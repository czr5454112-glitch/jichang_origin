#!/usr/bin/env python3
"""Plan and compact the targeted G23 Source ADMIT/HOLD pilot.

The module intentionally contains no simulator of its own.  It selects real
``storage_out`` opportunities at node 52, emits a small same-front
ADMIT-versus-one-opportunity-HOLD contract, and optionally forwards those
targets to the existing native exact-pair entry point.  Selection consumes
only pre-action local observations; outcome fields are never copied into a
target or used for ranking.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean, median
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

RESEARCH_PROFILE = "G23_A0_S4_J2_E2"
CENSUS_SCHEMA = "czr005.g4irsf23.source_admission_census.v1"
GROUP_SCHEMA = "czr005.g4irsf23.source_pilot_group.v1"
TARGET_SCHEMA = "czr005.g4irsf23.source_admit_hold_target.v1"
PLAN_SCHEMA = "czr005.g4irsf23.source_pilot_plan.v1"
LABEL_SCHEMA = "czr005.g4irsf23.source_fair_label.v1"
SUMMARY_SCHEMA = "czr005.g4irsf23.source_pilot_summary.v1"
MERGED_PAIR_SCHEMA = "czr005.g4irsf23.merged_exact_pair_payload.v1"
PAIR_SHARD_MANIFEST_SCHEMA = "czr005.g4irsf23.source_pair_shard_manifest.v1"

TARGET_NODE = 52
TARGET_LEG = "storage_out"
BLOCK_GROUP_TARGETS = {7: 192, 8: 64}
BLOCK_H_SYSTEM_TARGETS = {7: 128, 8: 48}
HORIZONS = ("H_bag", "H_system")

MEAN_EFFECT_EPSILON_SECONDS = 0.001
TAIL_TOLERANCE_SECONDS = 0.001
USABLE_SYSTEM_GAIN_SECONDS = 0.01
STRONG_SYSTEM_GAIN_SECONDS = 0.05

LOCAL_CONTEXT_FIELDS = (
    "candidate_deadline_slack_seconds",
    "candidate_wait_age_seconds",
    "already_held",
    "source_queue_length",
    "source_queue_capacity",
    "source_queue_utilization",
    "source_queue_generation_delta",
    "release_count_10s",
    "release_count_30s",
    "release_count_60s",
    "admission_count_10s",
    "admission_count_30s",
    "admission_count_60s",
    "queue_slope_10s",
    "queue_slope_30s",
    "queue_slope_60s",
    "time_to_next_service_opportunity_seconds",
    "estimated_service_rate_60s",
    "target_queue_length",
    "target_queue_capacity",
    "target_queue_utilization",
    "target_scheduled_incoming",
    "target_next_available",
    "first_edge_credit_slack_seconds",
    "merge_pending_count",
)


class SourcePilotError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourcePilotError(message)


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


def _first(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def _nested_mapping(row: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = row.get(name)
    return value if isinstance(value, Mapping) else {}


def _source_context(row: Mapping[str, Any]) -> dict[str, Any]:
    candidates: list[Mapping[str, Any]] = [row]
    for name in ("outcome_free_context", "source_context", "local_context", "observation"):
        candidates.append(_nested_mapping(row, name))
    pair = _nested_mapping(row, "observation_pair")
    candidates.append(_nested_mapping(pair, "baseline_observation"))

    context: dict[str, Any] = {}
    for field in LOCAL_CONTEXT_FIELDS:
        value = next((candidate[field] for candidate in candidates if field in candidate), None)
        if field == "already_held":
            if type(value) is bool:
                context[field] = value
            elif value in (0, 1, 0.0, 1.0):
                context[field] = bool(value)
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                context[field] = number
    return context


def _leg(row: Mapping[str, Any]) -> str:
    metadata = _nested_mapping(row, "offline_sampling_metadata")
    value = _first(row, "leg", "leg_type", default=metadata.get("leg"))
    if isinstance(value, str) and value:
        return value
    segment_id = _first(row, "segment_id", default=metadata.get("segment_id"))
    if isinstance(segment_id, str) and ":" in segment_id:
        return segment_id.rsplit(":", 1)[-1]
    bag_class = metadata.get("bag_class")
    if bag_class == "storage_in_out":
        return TARGET_LEG
    raise SourcePilotError("source opportunity omitted leg/segment_id")


def _release_block(row: Mapping[str, Any]) -> int:
    metadata = _nested_mapping(row, "offline_sampling_metadata")
    value = _first(
        row,
        "release_block",
        "release_time_block",
        "block",
        default=metadata.get("release_block"),
    )
    if value is None:
        release = _first(row, "release_time", default=metadata.get("release_time"))
        value = int(_finite(release, "release_time", minimum=0.0) // 3600.0)
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return _integer(value, "release_block", minimum=0)


def normalize_source_opportunity(
    row: Mapping[str, Any],
    *,
    require_target_block: bool = True,
) -> dict[str, Any]:
    """Validate one native late-legal Source admission opportunity.

    The dedicated schema and explicit legality bits are mandatory.  In
    particular, an old I1 ready-list row cannot be reinterpreted as proof
    that A0 reached the post-legality, pre-reservation admission seam.
    """

    schema = _first(row, "schema", "schema_id")
    native_schema = (
        row.get("native_census_schema") if schema == GROUP_SCHEMA else schema
    )
    _require(native_schema == CENSUS_SCHEMA, "expected native G23 Source admission census schema")
    _require(row.get("baseline_release") is True, "late legal seam must set baseline_release=true")
    _require(row.get("baseline_admit_legal") is True, "baseline ADMIT is not explicitly legal")

    runtime_bag_id = _integer(row.get("runtime_bag_id"), "runtime_bag_id", minimum=0)
    event_ordinal = _integer(row.get("event_ordinal"), "event_ordinal", minimum=0)
    event_time = _finite(row.get("event_time"), "event_time", minimum=0.0)
    metadata = _nested_mapping(row, "offline_sampling_metadata")
    node = _first(row, "node", "source_node", "current_node", default=metadata.get("source_node"))
    node = _integer(node, "node")
    leg = _leg(row)
    release_block = _release_block(row)

    _require(leg == TARGET_LEG, f"expected {TARGET_LEG}, got {leg}")
    _require(node == TARGET_NODE, f"expected node {TARGET_NODE}, got {node}")
    if require_target_block:
        _require(release_block in BLOCK_GROUP_TARGETS, "release block must be 7 or 8")
    _require(row.get("fault_active", False) is False, "fault-active opportunity")
    _require(row.get("stale_generation", False) is False, "stale source generation")

    ready = row.get("source_ready_order")
    front = _first(row, "front_runtime_bag_id", "source_front_runtime_bag_id")
    if front is None and isinstance(ready, list) and ready:
        front = ready[0]
    if front is None:
        front = runtime_bag_id
    front = _integer(front, "front_runtime_bag_id", minimum=0)
    _require(front == runtime_bag_id, "runtime bag is not the current source front")

    event_seq = row.get("event_seq")
    if event_seq is not None:
        event_seq = _integer(event_seq, "event_seq", minimum=0)
    task_id = row.get("task_id", metadata.get("task_id"))
    if task_id is not None:
        task_id = _integer(task_id, "task_id", minimum=0)
    segment_id = row.get("segment_id", metadata.get("segment_id"))

    context = _source_context(row)
    group_id = _first(
        row,
        "source_group_id",
        "source_opportunity_id",
        "census_id",
        "population_selection_id",
        "descriptor_id",
    )
    if not isinstance(group_id, str) or not group_id:
        group_id = f"source-{event_ordinal}-{runtime_bag_id}"
    normalized: dict[str, Any] = {
        "schema": GROUP_SCHEMA,
        "native_census_schema": CENSUS_SCHEMA,
        "source_group_id": group_id,
        "event_ordinal": event_ordinal,
        "event_time": event_time,
        "runtime_bag_id": runtime_bag_id,
        "front_runtime_bag_id": front,
        "node": node,
        "leg": leg,
        "release_block": release_block,
        "baseline_action": "ADMIT_NOW",
        "baseline_release": True,
        "baseline_admit_legal": True,
        "treatment_action": "HOLD_ONE_NATURAL_OPPORTUNITY",
        "outcome_free_context": context,
    }
    if event_seq is not None:
        normalized["event_seq"] = event_seq
    if task_id is not None:
        normalized["task_id"] = task_id
    if isinstance(segment_id, str) and segment_id:
        normalized["segment_id"] = segment_id
    return normalized


def _bucket(value: float, low: float, high: float) -> str:
    if value <= low:
        return "low"
    if value <= high:
        return "mid"
    return "high"


def outcome_free_stratum(group: Mapping[str, Any]) -> str:
    context = _nested_mapping(group, "outcome_free_context")
    source_queue = float(context.get("source_queue_length", 0.0))
    downstream = float(context.get("target_queue_length", 0.0)) + float(
        context.get("target_scheduled_incoming", 0.0)
    )
    service_gap = float(context.get("time_to_next_service_opportunity_seconds", 0.0))
    slope = float(context.get("queue_slope_30s", 0.0))
    time_block = int(float(group["event_time"]) // 900.0)
    return "|".join(
        (
            f"source_{_bucket(source_queue, 16.0, 32.0)}",
            f"downstream_{_bucket(downstream, 4.0, 16.0)}",
            f"service_{_bucket(service_gap, 1.0, 5.0)}",
            "rising" if slope > 0.0 else "flat_or_falling",
            f"t{time_block}",
        )
    )


def _selection_score(group: Mapping[str, Any]) -> float:
    context = _nested_mapping(group, "outcome_free_context")
    return (
        float(context.get("source_queue_length", 0.0))
        + float(context.get("target_queue_length", 0.0))
        + float(context.get("target_scheduled_incoming", 0.0))
        + 30.0 * max(0.0, float(context.get("queue_slope_30s", 0.0)))
        + float(context.get("time_to_next_service_opportunity_seconds", 0.0))
    )


def _diverse_prefix(rows: Sequence[Mapping[str, Any]], count: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        row["selection_stratum"] = outcome_free_stratum(row)
        row["selection_score"] = _selection_score(row)
        buckets[row["selection_stratum"]].append(row)
    for values in buckets.values():
        values.sort(
            key=lambda row: (
                -float(row["selection_score"]),
                int(row["event_ordinal"]),
                int(row["runtime_bag_id"]),
            )
        )
    order = sorted(buckets, key=lambda key: (-buckets[key][0]["selection_score"], key))
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


def select_source_pilot_groups(
    rows: Iterable[Mapping[str, Any]],
    *,
    block_group_targets: Mapping[int, int] = BLOCK_GROUP_TARGETS,
    block_h_system_targets: Mapping[int, int] = BLOCK_H_SYSTEM_TARGETS,
    require_complete: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select block quotas with one opportunity per runtime bag globally."""

    requested_blocks = tuple(sorted(block_group_targets))
    _require(
        set(requested_blocks) <= set(BLOCK_GROUP_TARGETS),
        "target release blocks must be 7 or 8",
    )
    _require(set(block_h_system_targets) <= set(block_group_targets), "unknown H_system block")
    for block, requested in block_group_targets.items():
        _require(type(requested) is int and requested >= 0, f"bad block {block} target")
        h_count = block_h_system_targets.get(block, 0)
        _require(type(h_count) is int and 0 <= h_count <= requested, f"bad block {block} H_system target")

    eligible: dict[int, list[dict[str, Any]]] = defaultdict(list)
    rejected_count = 0
    out_of_scope_release_block_count = 0
    for raw in rows:
        try:
            row = normalize_source_opportunity(raw, require_target_block=False)
        except (SourcePilotError, TypeError):
            rejected_count += 1
            continue
        if row["release_block"] not in requested_blocks:
            out_of_scope_release_block_count += 1
            continue
        eligible[int(row["release_block"])].append(row)

    selected: list[dict[str, Any]] = []
    used_bags: set[int] = set()
    per_block: dict[str, Any] = {}
    for block in requested_blocks:
        available = [row for row in eligible[block] if row["runtime_bag_id"] not in used_bags]
        # Collapse repeated events for one bag before diversity selection.
        best_by_bag: dict[int, dict[str, Any]] = {}
        for row in available:
            bag = int(row["runtime_bag_id"])
            incumbent = best_by_bag.get(bag)
            if incumbent is None or (
                -_selection_score(row), row["event_ordinal"]
            ) < (-_selection_score(incumbent), incumbent["event_ordinal"]):
                best_by_bag[bag] = row
        block_rows = _diverse_prefix(
            list(best_by_bag.values()), int(block_group_targets[block])
        )
        h_system_count = min(int(block_h_system_targets.get(block, 0)), len(block_rows))
        for index, row in enumerate(block_rows):
            row["assigned_horizons"] = list(HORIZONS if index < h_system_count else ("H_bag",))
            used_bags.add(int(row["runtime_bag_id"]))
            selected.append(row)
        per_block[str(block)] = {
            "requested_groups": int(block_group_targets[block]),
            "selected_groups": len(block_rows),
            "group_shortfall": max(0, int(block_group_targets[block]) - len(block_rows)),
            "requested_h_system": int(block_h_system_targets.get(block, 0)),
            "selected_h_system": h_system_count,
            "h_system_shortfall": max(0, int(block_h_system_targets.get(block, 0)) - h_system_count),
            "outcome_free_strata": len({row["selection_stratum"] for row in block_rows}),
        }

    complete = all(
        item["group_shortfall"] == 0 and item["h_system_shortfall"] == 0
        for item in per_block.values()
    )
    if require_complete:
        _require(complete, "source pilot quota is incomplete")
    audit = {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "rejected_row_count": rejected_count,
        "out_of_scope_release_block_count": out_of_scope_release_block_count,
        "runtime_bag_ids_are_unique": len(used_bags) == len(selected),
        "blocks": per_block,
    }
    return selected, audit


def build_source_targets(groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for raw in groups:
        group = normalize_source_opportunity(raw)
        horizons = raw.get("assigned_horizons", ["H_bag"])
        _require(
            isinstance(horizons, list)
            and horizons
            and all(value in HORIZONS for value in horizons),
            "invalid assigned_horizons",
        )
        for horizon in horizons:
            target_id = f"{group['source_group_id']}:{horizon}"
            event_time = _finite(group["event_time"], "event_time", minimum=0.0)
            task_group_id = group.get("task_id", group["source_group_id"])
            pressure_episode_id = raw.get("selection_stratum") or outcome_free_stratum(
                group
            )
            targets.append(
                {
                    "schema": TARGET_SCHEMA,
                    "target_id": target_id,
                    "source_group_id": group["source_group_id"],
                    "research_profile": RESEARCH_PROFILE,
                    "kind": "SOURCE_ADMISSION",
                    "intervention_kind": "SOURCE_HOLD_ONE_NATURAL_OPPORTUNITY",
                    "baseline_action": "ADMIT_NOW",
                    "treatment_action": "HOLD_ONE_NATURAL_OPPORTUNITY",
                    "expected_action_change_type": "SOURCE_ADMISSION_ONE_OPPORTUNITY_HOLD",
                    "horizon": horizon,
                    "event_ordinal": group["event_ordinal"],
                    "event_time": event_time,
                    "event_seq": group.get("event_seq"),
                    "runtime_bag_id": group["runtime_bag_id"],
                    "front_runtime_bag_id": group["runtime_bag_id"],
                    "task_id": group.get("task_id"),
                    "segment_id": group.get("segment_id"),
                    # These are outcome-free leakage barriers for the later
                    # train/held-out split.  Freeze them in the target rather
                    # than reconstructing them from native outcomes.
                    "task_group_id": task_group_id,
                    "contiguous_block_id": math.floor(event_time / 900.0),
                    "pressure_episode_id": pressure_episode_id,
                    "node": TARGET_NODE,
                    "leg": TARGET_LEG,
                    "release_block": group["release_block"],
                    "baseline_release": True,
                    "baseline_admit_legal": True,
                    "selection_stratum": pressure_episode_id,
                    "preserve_front_bag": True,
                    "max_hold_opportunities": 1,
                    "force_a0_after_hold": True,
                    "outcome_free": True,
                    "outcome_free_context": dict(group["outcome_free_context"]),
                }
            )
    _require(len({row["target_id"] for row in targets}) == len(targets), "duplicate target_id")
    return targets


def build_source_pilot_plan(
    rows: Iterable[Mapping[str, Any]],
    *,
    block_group_targets: Mapping[int, int] = BLOCK_GROUP_TARGETS,
    block_h_system_targets: Mapping[int, int] = BLOCK_H_SYSTEM_TARGETS,
    require_complete: bool = False,
) -> dict[str, Any]:
    groups, selection = select_source_pilot_groups(
        rows,
        block_group_targets=block_group_targets,
        block_h_system_targets=block_h_system_targets,
        require_complete=require_complete,
    )
    targets = build_source_targets(groups)
    return {
        "schema": PLAN_SCHEMA,
        "research_profile": RESEARCH_PROFILE,
        "selection": selection,
        "groups": groups,
        "targets": targets,
        "counts": {
            "group_count": len(groups),
            "h_bag_group_count": len(groups),
            "h_system_group_count": sum("H_system" in row["assigned_horizons"] for row in groups),
            "target_count": len(targets),
        },
    }


def load_native_backend(binary: Path) -> Any:
    resolved = binary.resolve(strict=True)
    specification = importlib.util.spec_from_file_location("czr005_cpp", resolved)
    _require(specification is not None and specification.loader is not None, "cannot load native backend")
    module = importlib.util.module_from_spec(specification)
    sys.modules["czr005_cpp"] = module
    specification.loader.exec_module(module)
    return module


def build_2x_native_arguments(
    root: Path = ROOT,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Reuse the frozen G22 constructor for the exact 87,206-segment input."""

    from scripts.eval import run_g4irsf22_action_timing as g22

    return g22.build_2x_native_arguments(root)


def scan_native_source_opportunities(
    backend: Any,
    native_arguments: Sequence[Any],
) -> list[dict[str, Any]]:
    """Run the dedicated native late-legal Source census on the 2x stream."""

    scan = getattr(
        backend,
        "g4irsf23_scan_source_admission_opportunities_from_records",
        None,
    )
    _require(callable(scan), "native backend omitted the G23 Source admission census API")
    payload = scan(*native_arguments, RESEARCH_PROFILE)
    _require(isinstance(payload, Mapping), "native Source census returned no object")
    _require(payload.get("census_complete") is True, "native Source census did not complete")
    rows = payload.get("opportunities")
    _require(isinstance(rows, list), "native Source census omitted opportunities")
    return [
        normalize_source_opportunity(row, require_target_block=False)
        for row in rows
        if isinstance(row, Mapping)
    ]


def run_native_exact_pairs(
    backend: Any,
    native_arguments: Sequence[Any],
    targets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Thin adapter to the existing exact same-state native pair API."""

    run = getattr(backend, "g4irsf15_run_causal_target_pairs_from_records", None)
    _require(callable(run), "native backend omitted the exact pair API")
    payload = run(
        *native_arguments,
        [dict(target) for target in targets],
        RESEARCH_PROFILE,
    )
    _require(isinstance(payload, Mapping), "native exact pair API returned no object")
    _require(isinstance(payload.get("pairs"), list), "native exact pair API omitted pairs")
    return dict(payload)


def select_pair_targets(
    targets: Sequence[Mapping[str, Any]],
    *,
    horizon: str = "all",
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return one deterministic execution slice without changing the plan."""

    _require(horizon in {"all", *HORIZONS}, "pair horizon must be all, H_bag, or H_system")
    _require(type(offset) is int and offset >= 0, "pair offset must be >= 0")
    _require(limit is None or (type(limit) is int and limit >= 1), "pair limit must be >= 1")
    eligible = [
        dict(target)
        for target in targets
        if horizon == "all" or target.get("horizon") == horizon
    ]
    return eligible[offset:] if limit is None else eligible[offset : offset + limit]


def select_pair_manifest_shard(
    targets: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    shard_id: str,
) -> list[dict[str, Any]]:
    """Resolve one manifest shard to exact plan targets in manifest order."""

    _require(
        manifest.get("schema") == PAIR_SHARD_MANIFEST_SCHEMA,
        "pair shard manifest has the wrong schema",
    )
    _require(isinstance(shard_id, str) and shard_id, "pair shard id is required")
    shards = manifest.get("shards")
    _require(isinstance(shards, list), "pair shard manifest omitted shards")
    matches = [
        shard
        for shard in shards
        if isinstance(shard, Mapping) and shard.get("shard_id") == shard_id
    ]
    _require(len(matches) == 1, f"pair shard id must match exactly once: {shard_id}")
    target_ids = matches[0].get("target_ids")
    _require(
        isinstance(target_ids, list)
        and target_ids
        and all(isinstance(target_id, str) and target_id for target_id in target_ids),
        f"pair shard {shard_id} has no valid target_ids",
    )
    _require(
        len(set(target_ids)) == len(target_ids),
        f"pair shard {shard_id} contains duplicate target_ids",
    )
    expected_count = matches[0].get("target_count")
    if expected_count is not None:
        _require(
            expected_count == len(target_ids),
            f"pair shard {shard_id} target_count disagrees with target_ids",
        )
    target_by_id: dict[str, dict[str, Any]] = {}
    for target in targets:
        target_id = _target_id(target, "plan target")
        _require(target_id not in target_by_id, f"duplicate plan target_id: {target_id}")
        target_by_id[target_id] = dict(target)
    unknown = [target_id for target_id in target_ids if target_id not in target_by_id]
    _require(not unknown, f"pair shard {shard_id} has unknown target_ids: {unknown}")
    selected = [target_by_id[target_id] for target_id in target_ids]
    horizon = matches[0].get("horizon")
    if horizon is not None:
        _require(horizon in HORIZONS, f"pair shard {shard_id} has invalid horizon")
        _require(
            all(target.get("horizon") == horizon for target in selected),
            f"pair shard {shard_id} mixes horizons",
        )
    return selected


def _target_id(row: Mapping[str, Any], label: str) -> str:
    value = row.get("target_id")
    _require(isinstance(value, str) and value, f"{label} omitted target_id")
    return value


def merge_pair_payloads(
    payloads: Sequence[Mapping[str, Any]],
    expected_targets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge resumable native shards by exact target ID.

    Identical overlap is accepted so an interrupted shard may be rerun safely;
    non-identical overlap fails closed.  The expected target list is an
    allow-list and also supplies explicit coverage counts.  Partial merges are
    valid recovery artifacts and never claim full coverage.
    """

    expected_by_id: dict[str, Mapping[str, Any]] = {}
    for target in expected_targets:
        target_id = _target_id(target, "expected target")
        _require(target_id not in expected_by_id, f"duplicate expected target_id: {target_id}")
        expected_by_id[target_id] = target

    pair_by_id: dict[str, dict[str, Any]] = {}
    duplicate_pair_count = 0
    payload_pair_counts: list[int] = []
    for payload_index, payload in enumerate(payloads):
        _require(isinstance(payload, Mapping), f"pair payload {payload_index} is not an object")
        pairs = payload.get("pairs")
        _require(isinstance(pairs, list), f"pair payload {payload_index} omitted pairs")
        payload_pair_counts.append(len(pairs))
        for pair_index, raw_pair in enumerate(pairs):
            _require(
                isinstance(raw_pair, Mapping),
                f"pair payload {payload_index} pair {pair_index} is not an object",
            )
            pair = dict(raw_pair)
            target_id = _target_id(pair, "native pair")
            _require(target_id in expected_by_id, f"unexpected pair target_id: {target_id}")
            expected = expected_by_id[target_id]
            for field in ("source_group_id", "horizon", "event_ordinal", "runtime_bag_id"):
                if expected.get(field) is not None and pair.get(field) is not None:
                    _require(
                        pair.get(field) == expected.get(field),
                        f"pair {target_id} conflicts with expected {field}",
                    )
            incumbent = pair_by_id.get(target_id)
            if incumbent is not None:
                _require(incumbent == pair, f"conflicting duplicate pair target_id: {target_id}")
                duplicate_pair_count += 1
                continue
            pair_by_id[target_id] = pair

    ordered_pairs = [
        pair_by_id[target_id]
        for target_id in expected_by_id
        if target_id in pair_by_id
    ]
    missing_target_ids = [
        target_id for target_id in expected_by_id if target_id not in pair_by_id
    ]
    expected_horizon_counts = {
        horizon: sum(target.get("horizon") == horizon for target in expected_targets)
        for horizon in HORIZONS
    }
    observed_horizon_counts = {
        horizon: sum(pair.get("horizon") == horizon for pair in ordered_pairs)
        for horizon in HORIZONS
    }
    expected_groups = {
        str(target["source_group_id"])
        for target in expected_targets
        if isinstance(target.get("source_group_id"), str)
    }
    observed_groups = {
        str(pair["source_group_id"])
        for pair in ordered_pairs
        if isinstance(pair.get("source_group_id"), str)
    }
    action_changed_groups = action_changed_source_group_count({"pairs": ordered_pairs})
    return {
        "schema": MERGED_PAIR_SCHEMA,
        "pairs": ordered_pairs,
        "target_count": len(ordered_pairs),
        "input_payload_count": len(payloads),
        "input_payload_pair_counts": payload_pair_counts,
        "duplicate_pair_count": duplicate_pair_count,
        "expected_target_count": len(expected_by_id),
        "missing_target_count": len(missing_target_ids),
        "missing_target_ids": missing_target_ids,
        "coverage_complete": not missing_target_ids,
        "expected_horizon_counts": expected_horizon_counts,
        "observed_horizon_counts": observed_horizon_counts,
        "expected_unique_group_count": len(expected_groups),
        "observed_unique_group_count": len(observed_groups),
        "action_changed_unique_group_count": action_changed_groups,
    }


def _contiguous_target_shards(
    targets: Sequence[Mapping[str, Any]],
    *,
    horizon: str,
    shard_size: int,
) -> list[dict[str, Any]]:
    _require(horizon in HORIZONS, "shard horizon must be H_bag or H_system")
    _require(type(shard_size) is int and shard_size >= 1, "shard size must be >= 1")
    ordered = sorted(
        (dict(target) for target in targets if target.get("horizon") == horizon),
        key=lambda target: (
            _integer(target.get("event_ordinal"), "target.event_ordinal", minimum=0),
            _integer(target.get("runtime_bag_id"), "target.runtime_bag_id", minimum=0),
            _target_id(target, "target"),
        ),
    )
    shards: list[dict[str, Any]] = []
    for offset in range(0, len(ordered), shard_size):
        rows = ordered[offset : offset + shard_size]
        shards.append(
            {
                "shard_id": f"{horizon.lower()}-{len(shards):03d}",
                "horizon": horizon,
                "target_count": len(rows),
                "target_ids": [_target_id(row, "target") for row in rows],
                "plan_offsets": [int(row["_plan_offset"]) for row in rows],
                "cli_slices": [
                    {
                        "pair_horizon": horizon,
                        "pair_offset": int(row["_horizon_offset"]),
                        "pair_limit": 1,
                    }
                    for row in rows
                ],
                "min_event_ordinal": min(int(row["event_ordinal"]) for row in rows),
                "max_event_ordinal": max(int(row["event_ordinal"]) for row in rows),
                "event_ordinal_contiguous_slice": True,
            }
        )
    return shards


def build_pair_shard_manifest(
    targets: Sequence[Mapping[str, Any]],
    *,
    h_system_shard_size: int = 8,
    h_bag_remainder_shard_size: int = 20,
    workers: int = 4,
) -> dict[str, Any]:
    """Plan, but never launch, the formal Source exact-pair process farm.

    H_system covers the formal 176-group subset.  Those groups do not need a
    separate H_bag replay for the action-changing denominator because the
    completed H_system certificate proves the same immediate action change.
    Only the remaining 80 groups receive H_bag shards.
    """

    _require(type(workers) is int and workers >= 1, "workers must be >= 1")
    by_group: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for plan_offset, raw_target in enumerate(targets):
        target = {**dict(raw_target), "_plan_offset": plan_offset}
        group = target.get("source_group_id")
        horizon = target.get("horizon")
        _require(isinstance(group, str) and group, "target omitted source_group_id")
        _require(horizon in HORIZONS, "target has invalid horizon")
        _require(horizon not in by_group[group], f"duplicate {horizon} target for {group}")
        by_group[group][str(horizon)] = target
    for horizon in HORIZONS:
        horizon_rows = [
            target
            for rows in by_group.values()
            for name, target in rows.items()
            if name == horizon
        ]
        horizon_rows.sort(key=lambda target: int(target["_plan_offset"]))
        for horizon_offset, target in enumerate(horizon_rows):
            target["_horizon_offset"] = horizon_offset
    system_groups = {
        group for group, rows in by_group.items() if "H_system" in rows
    }
    h_system_targets = [by_group[group]["H_system"] for group in system_groups]
    h_bag_remainder_targets = [
        rows["H_bag"]
        for group, rows in by_group.items()
        if group not in system_groups and "H_bag" in rows
    ]
    shards = _contiguous_target_shards(
        h_system_targets, horizon="H_system", shard_size=h_system_shard_size
    )
    shards.extend(
        _contiguous_target_shards(
            h_bag_remainder_targets,
            horizon="H_bag",
            shard_size=h_bag_remainder_shard_size,
        )
    )
    expected_execution_target_count = sum(int(shard["target_count"]) for shard in shards)
    return {
        "schema": PAIR_SHARD_MANIFEST_SCHEMA,
        "execution_default": "PLAN_ONLY_DO_NOT_START_PROCESSES",
        "max_workers": workers,
        "partition_order": "CONTIGUOUS_EVENT_ORDINAL",
        "h_system_group_count": len(h_system_targets),
        "h_bag_remainder_group_count": len(h_bag_remainder_targets),
        "covered_unique_group_count": len(system_groups) + len(h_bag_remainder_targets),
        "expected_execution_target_count": expected_execution_target_count,
        "shard_count": len(shards),
        "shards": shards,
    }


def _metric(pair: Mapping[str, Any], name: str) -> float:
    value = pair.get(name)
    if value is not None:
        return _finite(value, name)
    baseline = _nested_mapping(pair, "baseline")
    treatment = _nested_mapping(pair, "treatment")
    aliases = {
        "system_mean_delta_seconds": ("raw_bag_mean_tth_seconds", "completion_mean_seconds"),
        "system_p95_delta_seconds": ("raw_bag_p95_tth_seconds", "completion_p95_seconds"),
        "system_p99_delta_seconds": ("raw_bag_p99_tth_seconds", "completion_p99_seconds"),
        "deadline_miss_delta": ("deadline_miss_count",),
    }
    for alias in aliases.get(name, ()):
        left = baseline.get(alias, _nested_mapping(baseline, "cohort_metrics").get(alias))
        right = treatment.get(alias, _nested_mapping(treatment, "cohort_metrics").get(alias))
        if left is not None and right is not None:
            return _finite(right, f"treatment.{alias}") - _finite(left, f"baseline.{alias}")
    raise SourcePilotError(f"pair omitted {name}")


def _certificate_value(pair: Mapping[str, Any], name: str, default: Any = None) -> Any:
    certificate = _nested_mapping(pair, "action_change_certificate")
    return pair.get(name, certificate.get(name, default))


def _label_metadata_from_target(target: Mapping[str, Any]) -> dict[str, Any]:
    """Return the authoritative outcome-free fields for one compact label."""

    context = target.get("outcome_free_context")
    _require(isinstance(context, Mapping), "target omitted outcome_free_context")
    task_id = target.get("task_id")
    _require(task_id is not None, "target omitted task_id")
    segment_id = target.get("segment_id")
    _require(isinstance(segment_id, str) and segment_id, "target omitted segment_id")
    event_time = _finite(target.get("event_time"), "target.event_time", minimum=0.0)
    selection_stratum = target.get("selection_stratum")
    _require(
        isinstance(selection_stratum, str) and selection_stratum,
        "target omitted selection_stratum",
    )
    task_group_id = target.get("task_group_id", task_id)
    contiguous_block_id = target.get(
        "contiguous_block_id", math.floor(event_time / 900.0)
    )
    pressure_episode_id = target.get("pressure_episode_id", selection_stratum)
    _require(task_group_id is not None, "target omitted task_group_id")
    _require(contiguous_block_id is not None, "target omitted contiguous_block_id")
    _require(pressure_episode_id is not None, "target omitted pressure_episode_id")
    return {
        "task_id": task_id,
        "segment_id": segment_id,
        "event_time": event_time,
        "event_seq": target.get("event_seq"),
        "task_group_id": task_group_id,
        "contiguous_block_id": contiguous_block_id,
        "pressure_episode_id": pressure_episode_id,
        "outcome_free_context": dict(context),
    }


def compact_fair_label(
    pair: Mapping[str, Any], target: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Reduce one H_system exact pair to system effect plus fairness gates."""

    _require(pair.get("horizon") == "H_system", "fair labels require H_system")
    mean = _metric(pair, "system_mean_delta_seconds")
    p95 = _metric(pair, "system_p95_delta_seconds")
    p99 = _metric(pair, "system_p99_delta_seconds")
    deadline = int(_metric(pair, "deadline_miss_delta"))
    current_cost = _finite(pair.get("current_bag_cost_seconds"), "current_bag_cost_seconds")
    opportunity = _finite(
        pair.get("natural_opportunity_seconds"),
        "natural_opportunity_seconds",
        minimum=0.0,
    )

    changed = _certificate_value(pair, "action_changed", False) is True
    exactly_one = _certificate_value(pair, "changed_action_count", 0) == 1
    same_front = _certificate_value(pair, "front_bag_unchanged", False) is True
    # These three fields must be emitted only after the native branch has
    # advanced beyond the held service opportunity.  The immediate action
    # certificate's *_contract_configured fields are design declarations and
    # deliberately do not satisfy this evidence gate.
    hold_count = pair.get("hold_opportunity_count_observed", 0)
    forced_a0 = pair.get("forced_a0_after_hold_observed", False) is True
    repeated = pair.get("repeated_hold_count_observed", 0)
    horizon_complete = pair.get("horizon_complete", True) is True
    hard_safe = pair.get("hard_gate_pass", True) is True
    contract_pass = (
        changed
        and exactly_one
        and same_front
        and hold_count == 1
        and forced_a0
        and repeated == 0
        and horizon_complete
        and hard_safe
    )
    individual_cost_pass = current_cost <= opportunity + TAIL_TOLERANCE_SECONDS
    deadline_pass = deadline <= 0
    tail_pass = p95 <= TAIL_TOLERANCE_SECONDS and p99 <= TAIL_TOLERANCE_SECONDS
    system_beneficial = mean <= -MEAN_EFFECT_EPSILON_SECONDS
    harmful = mean > MEAN_EFFECT_EPSILON_SECONDS or not tail_pass
    fairness_pass = contract_pass and individual_cost_pass and deadline_pass

    if harmful:
        label = "HARMFUL"
    elif system_beneficial and fairness_pass:
        label = "FAIR_SYSTEM_BENEFICIAL"
    elif system_beneficial:
        label = "SYSTEM_BENEFICIAL_BUT_UNFAIR"
    else:
        label = "NEUTRAL"

    if mean <= -STRONG_SYSTEM_GAIN_SECONDS:
        tier = "strong"
    elif mean <= -USABLE_SYSTEM_GAIN_SECONDS:
        tier = "usable"
    elif mean <= -MEAN_EFFECT_EPSILON_SECONDS:
        tier = "weak_diagnostic"
    elif abs(mean) < MEAN_EFFECT_EPSILON_SECONDS:
        tier = "neutral"
    else:
        tier = "harmful"

    compact = {
        "schema": LABEL_SCHEMA,
        "target_id": pair.get("target_id"),
        "source_group_id": pair.get("source_group_id"),
        "runtime_bag_id": pair.get("runtime_bag_id"),
        "task_id": pair.get("task_id"),
        "event_ordinal": pair.get("event_ordinal"),
        "release_block": pair.get("release_block"),
        "selection_stratum": pair.get("selection_stratum"),
        "label": label,
        "effect_tier": tier,
        "system_mean_delta_seconds": mean,
        "system_p95_delta_seconds": p95,
        "system_p99_delta_seconds": p99,
        "current_bag_cost_seconds": current_cost,
        "natural_opportunity_seconds": opportunity,
        "deadline_miss_delta": deadline,
        "gates": {
            "exact_one_opportunity_contract": contract_pass,
            "individual_cost": individual_cost_pass,
            "deadline": deadline_pass,
            "tail": tail_pass,
            "fairness": fairness_pass,
            "promotion_strength": label == "FAIR_SYSTEM_BENEFICIAL"
            and tier in {"strong", "usable"},
        },
    }
    if target is not None:
        compact.update(_label_metadata_from_target(target))
    return compact


def compact_fair_labels(
    payload: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    pairs = payload.get("pairs")
    _require(isinstance(pairs, list), "pair payload omitted pairs")
    target_by_id: dict[str, Mapping[str, Any]] = {}
    for target in targets:
        target_id = _target_id(target, "label target")
        _require(target_id not in target_by_id, f"duplicate label target_id: {target_id}")
        target_by_id[target_id] = target
    labels: list[dict[str, Any]] = []
    for pair in pairs:
        if not isinstance(pair, Mapping) or pair.get("horizon") != "H_system":
            continue
        # A native screening false positive has no complete system outcome.
        # Preserve it in the action-changing denominator, but never fabricate
        # an effect label from missing metrics.
        if pair.get("action_changed") is not True or pair.get("pair_complete") is not True:
            continue
        target_id = _target_id(pair, "H_system pair")
        target = target_by_id.get(target_id)
        _require(target is not None, f"H_system pair has no matching target: {target_id}")
        for field in (
            "source_group_id",
            "horizon",
            "event_ordinal",
            "runtime_bag_id",
            "release_block",
            "selection_stratum",
        ):
            _require(
                pair.get(field) == target.get(field),
                f"pair {target_id} conflicts with target {field}",
            )
        labels.append(compact_fair_label(pair, target))
    return labels


def pair_execution_coverage(
    payload: Mapping[str, Any], targets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Audit the formal 176 H_system + 80 remainder execution allow-list."""

    manifest = build_pair_shard_manifest(targets)
    expected_ids = {
        target_id
        for shard in manifest["shards"]
        for target_id in shard["target_ids"]
    }
    target_by_id = {_target_id(target, "coverage target"): target for target in targets}
    _require(len(target_by_id) == len(targets), "duplicate coverage target_id")
    pairs = payload.get("pairs")
    _require(isinstance(pairs, list), "pair payload omitted pairs")
    observed_ids: set[str] = set()
    duplicate_count = 0
    for pair in pairs:
        if not isinstance(pair, Mapping):
            raise SourcePilotError("pair payload contains a non-object")
        target_id = _target_id(pair, "coverage pair")
        _require(target_id in target_by_id, f"coverage pair has unknown target_id: {target_id}")
        target = target_by_id[target_id]
        for field in (
            "source_group_id",
            "horizon",
            "event_ordinal",
            "runtime_bag_id",
            "release_block",
        ):
            if target.get(field) is not None:
                _require(
                    pair.get(field) == target.get(field),
                    f"coverage pair {target_id} conflicts with target {field}",
                )
        if target_id in observed_ids:
            duplicate_count += 1
        observed_ids.add(target_id)
    _require(duplicate_count == 0, "coverage payload contains duplicate target_id")
    missing_ids = sorted(expected_ids - observed_ids)
    payload_claim = payload.get("coverage_complete")
    _require(
        payload_claim is None or isinstance(payload_claim, bool),
        "coverage_complete must be boolean",
    )
    system_by_block = {
        block: sum(
            target_id in observed_ids
            and target_by_id[target_id].get("horizon") == "H_system"
            and target_by_id[target_id].get("release_block") == block
            for target_id in expected_ids
        )
        for block in BLOCK_H_SYSTEM_TARGETS
    }
    return {
        "coverage_complete": not missing_ids and payload_claim is not False,
        "expected_execution_target_count": len(expected_ids),
        "observed_execution_target_count": len(expected_ids & observed_ids),
        "missing_execution_target_count": len(missing_ids),
        "missing_execution_target_ids": missing_ids,
        "observed_h_system_by_block": system_by_block,
    }


def action_changed_source_group_count(payload: Mapping[str, Any]) -> int:
    """Count unique groups proved changed by a complete H_bag or H_system pair.

    H_system starts with the identical immediate Source intervention and keeps
    the same action certificate, so rerunning its group at H_bag is redundant.
    """

    pairs = payload.get("pairs")
    _require(isinstance(pairs, list), "pair payload omitted pairs")
    groups: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, Mapping) or pair.get("horizon") not in HORIZONS:
            continue
        certificate = _nested_mapping(pair, "action_change_certificate")
        if (
            pair.get("action_changed") is True
            and pair.get("pair_complete") is True
            and certificate.get("valid", True) is True
            and _certificate_value(pair, "changed_action_count", 0) == 1
        ):
            group = pair.get("source_group_id")
            if isinstance(group, str) and group:
                groups.add(group)
    return len(groups)


SOURCE_COMPONENT_MEAN_FIELDS = {
    "raw_bag_source_wait_mean_delta_seconds": "source_wait_mean_minutes",
    "raw_bag_network_time_mean_delta_seconds": "network_time_mean_minutes",
    "raw_bag_scheduled_pre_release_wait_mean_delta_seconds": (
        "scheduled_pre_release_wait_mean_minutes"
    ),
}


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    """Return the small descriptive panel used by compact G23 evidence."""

    _require(bool(values), "effect distribution has no values")
    ordered = sorted(float(value) for value in values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": fmean(ordered),
        "median": median(ordered),
        "max": ordered[-1],
        "nonzero_count": sum(value != 0.0 for value in ordered),
    }


def summarize_h_system_component_mean_deltas(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize Source wait decomposition from completed H_system pairs.

    Each delta is treatment minus baseline and is converted from minutes to
    seconds per protected raw bag.  This is an outcome description only; it
    does not add a gate or change the preregistered Source decision.
    """

    pairs = payload.get("pairs")
    _require(isinstance(pairs, list), "pair payload omitted pairs")
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        if not isinstance(pair, Mapping) or pair.get("horizon") != "H_system":
            continue
        _require(
            pair.get("pair_complete") is True
            and pair.get("horizon_complete", True) is True,
            "H_system component summary requires complete pairs",
        )
        baseline = _nested_mapping(
            _nested_mapping(pair, "baseline"), "raw_bag_cohort_metrics"
        )
        treatment = _nested_mapping(
            _nested_mapping(pair, "treatment"), "raw_bag_cohort_metrics"
        )
        _require(
            baseline.get("comparison_eligible") is True
            and treatment.get("comparison_eligible") is True,
            "H_system component summary requires comparable raw-bag metrics",
        )
        block = _integer(pair.get("release_block"), "release_block", minimum=0)
        row: dict[str, Any] = {"release_block": block}
        for output_name, raw_name in SOURCE_COMPONENT_MEAN_FIELDS.items():
            row[output_name] = 60.0 * (
                _finite(treatment.get(raw_name), f"treatment.{raw_name}")
                - _finite(baseline.get(raw_name), f"baseline.{raw_name}")
            )
        rows.append(row)

    _require(bool(rows), "pair payload has no complete H_system pairs")

    def summarize_scope(scope: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        _require(bool(scope), "H_system component scope is empty")
        return {
            "pair_count": len(scope),
            "metrics": {
                name: _distribution([float(row[name]) for row in scope])
                for name in SOURCE_COMPONENT_MEAN_FIELDS
            },
        }

    blocks = sorted({int(row["release_block"]) for row in rows})
    return {
        "unit": "seconds_per_complete_raw_bag",
        "delta_direction": "treatment_minus_baseline",
        "h_system_pair_count": len(rows),
        "release_block_pair_counts": {
            str(block): sum(row["release_block"] == block for row in rows)
            for block in blocks
        },
        "all": summarize_scope(rows),
        "by_release_block": {
            str(block): summarize_scope(
                [row for row in rows if row["release_block"] == block]
            )
            for block in blocks
        },
    }


def summarize_pilot_labels(
    labels: Sequence[Mapping[str, Any]],
    *,
    attempted_group_count: int = 256,
    action_changed_group_count: int | None = None,
    execution_coverage: Mapping[str, Any] | None = None,
    required_h_system_by_block: Mapping[int, int] = BLOCK_H_SYSTEM_TARGETS,
) -> dict[str, Any]:
    changed = len(labels) if action_changed_group_count is None else action_changed_group_count
    fair = [
        row
        for row in labels
        if row.get("label") == "FAIR_SYSTEM_BENEFICIAL"
        and row.get("effect_tier") in {"usable", "strong"}
        and _nested_mapping(row, "gates").get("promotion_strength") is True
    ]
    fair_block8 = [row for row in fair if row.get("release_block") == 8]
    strata = {row.get("selection_stratum") for row in fair if row.get("selection_stratum")}
    complete_rate = changed / attempted_group_count if attempted_group_count else 0.0
    coverage = dict(execution_coverage or {})
    observed_h_system_by_block = coverage.get("observed_h_system_by_block")
    if not isinstance(observed_h_system_by_block, Mapping):
        observed_h_system_by_block = {}
    gates = {
        "execution_coverage_complete": coverage.get("coverage_complete") is True,
        "h_system_coverage": all(
            observed_h_system_by_block.get(block, 0) >= required
            for block, required in required_h_system_by_block.items()
        ),
        "action_changing_rate": complete_rate >= 0.80,
        "fair_system_positive_count": len(fair) >= 16,
        "block8_fair_positive_count": len(fair_block8) >= 4,
        "positive_strata_coverage": len(strata) >= 3,
    }
    return {
        "schema": SUMMARY_SCHEMA,
        "attempted_group_count": attempted_group_count,
        "action_changed_group_count": changed,
        "action_changed_rate": complete_rate,
        "label_counts": {
            label: sum(row.get("label") == label for row in labels)
            for label in (
                "FAIR_SYSTEM_BENEFICIAL",
                "SYSTEM_BENEFICIAL_BUT_UNFAIR",
                "HARMFUL",
                "NEUTRAL",
            )
        },
        "block8_fair_positive_count": len(fair_block8),
        "promotion_eligible_fair_positive_count": len(fair),
        "fair_positive_strata_count": len(strata),
        "execution_coverage": coverage,
        "gates": gates,
        "pilot_support_pass": all(gates.values()),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            _require(isinstance(value, Mapping), f"{path}:{line_number} is not an object")
            rows.append(dict(value))
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--census-output", type=Path)
    parser.add_argument("--groups-output", type=Path, required=True)
    parser.add_argument("--targets-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--allow-shortfall", action="store_true")
    parser.add_argument(
        "--pair-results",
        type=Path,
        action="append",
        help="Repeat for resumable shard payloads; duplicates must be identical.",
    )
    parser.add_argument("--run-pairs", action="store_true")
    parser.add_argument("--pair-horizon", choices=("all", *HORIZONS), default="all")
    parser.add_argument("--pair-offset", type=int, default=0)
    parser.add_argument("--pair-limit", type=int)
    parser.add_argument("--pair-shard-manifest", type=Path)
    parser.add_argument("--pair-shard-id")
    parser.add_argument("--pairs-output", type=Path)
    parser.add_argument("--labels-output", type=Path)
    parser.add_argument("--shard-manifest-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        _require(
            not (arguments.pair_results and arguments.run_pairs),
            "--pair-results and --run-pairs are mutually exclusive",
        )
        has_shard_manifest = arguments.pair_shard_manifest is not None
        has_shard_id = arguments.pair_shard_id is not None
        _require(
            has_shard_manifest == has_shard_id,
            "--pair-shard-manifest and --pair-shard-id must appear together",
        )
        if has_shard_manifest:
            _require(
                arguments.pair_offset == 0 and arguments.pair_limit is None,
                "pair shard selection is mutually exclusive with --pair-offset/--pair-limit",
            )
            _require(
                arguments.pair_horizon == "all",
                "pair shard selection determines horizon; omit --pair-horizon",
            )
        _require(arguments.pair_offset >= 0, "--pair-offset must be >= 0")
        _require(arguments.pair_limit is None or arguments.pair_limit >= 1, "--pair-limit must be >= 1")
        backend = None
        native_arguments = None
        input_descriptor = None
        if arguments.binary is not None:
            backend = load_native_backend(arguments.binary)
        if arguments.census is not None:
            census = _read_jsonl(arguments.census)
        else:
            _require(backend is not None, "--binary is required without --census")
            native_arguments, _, input_descriptor = build_2x_native_arguments(ROOT)
            census = scan_native_source_opportunities(backend, native_arguments)
            if arguments.census_output is not None:
                # Persist the completed native census before quota selection so
                # a planner/configuration failure never forces another 2x scan.
                _write_jsonl(arguments.census_output, census)
        plan = build_source_pilot_plan(
            census,
            require_complete=not arguments.allow_shortfall,
        )
        _write_jsonl(arguments.groups_output, plan["groups"])
        _write_jsonl(arguments.targets_output, plan["targets"])
        summary: dict[str, Any] = {
            "schema": PLAN_SCHEMA,
            "research_profile": RESEARCH_PROFILE,
            "selection": plan["selection"],
            "input_descriptor": input_descriptor,
            **plan["counts"],
        }
        if has_shard_manifest:
            loaded_manifest = json.loads(
                arguments.pair_shard_manifest.read_text(encoding="utf-8")
            )
            _require(isinstance(loaded_manifest, Mapping), "pair shard manifest must be an object")
            pair_targets = select_pair_manifest_shard(
                plan["targets"], loaded_manifest, arguments.pair_shard_id
            )
            summary["pair_slice"] = {
                "selection_kind": "MANIFEST_SHARD",
                "shard_id": arguments.pair_shard_id,
                "manifest": str(arguments.pair_shard_manifest),
                "selected_target_count": len(pair_targets),
                "selected_target_ids": [target["target_id"] for target in pair_targets],
            }
        else:
            pair_targets = select_pair_targets(
                plan["targets"],
                horizon=arguments.pair_horizon,
                offset=arguments.pair_offset,
                limit=arguments.pair_limit,
            )
            summary["pair_slice"] = {
                "selection_kind": "OFFSET_LIMIT",
                "horizon": arguments.pair_horizon,
                "offset": arguments.pair_offset,
                "limit": arguments.pair_limit,
                "eligible_target_count": sum(
                    arguments.pair_horizon == "all"
                    or target.get("horizon") == arguments.pair_horizon
                    for target in plan["targets"]
                ),
                "selected_target_count": len(pair_targets),
            }
        if arguments.shard_manifest_output is not None:
            manifest = build_pair_shard_manifest(plan["targets"])
            _write_json(arguments.shard_manifest_output, manifest)
            summary["pair_shard_manifest"] = {
                key: value for key, value in manifest.items() if key != "shards"
            }
        pair_payload: Mapping[str, Any] | None = None
        if arguments.run_pairs:
            _require(backend is not None, "--run-pairs requires --binary")
            _require(pair_targets, "pair slice selected no targets")
            if native_arguments is None:
                native_arguments, _, input_descriptor = build_2x_native_arguments(ROOT)
                summary["input_descriptor"] = input_descriptor
            pair_payload = run_native_exact_pairs(backend, native_arguments, pair_targets)
            pairs_output = arguments.pairs_output or arguments.summary_output.with_suffix(
                ".pairs.json"
            )
            _write_json(pairs_output, pair_payload)
        elif arguments.pair_results:
            loaded_payloads: list[Mapping[str, Any]] = []
            for path in arguments.pair_results:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                _require(isinstance(loaded, Mapping), f"{path} pair results must be an object")
                loaded_payloads.append(loaded)
            # The recovery farm intentionally runs 176 H_system targets plus
            # only the remaining 80 H_bag targets, not all 432 plan targets.
            manifest = build_pair_shard_manifest(plan["targets"])
            execution_target_ids = {
                target_id
                for shard in manifest["shards"]
                for target_id in shard["target_ids"]
            }
            expected_execution_targets = [
                target
                for target in plan["targets"]
                if target.get("target_id") in execution_target_ids
            ]
            pair_payload = merge_pair_payloads(
                loaded_payloads, expected_execution_targets
            )
            summary["pair_merge"] = {
                key: value for key, value in pair_payload.items() if key != "pairs"
            }
            if arguments.pairs_output is not None:
                _write_json(arguments.pairs_output, pair_payload)
        if pair_payload is not None:
            _require(arguments.labels_output is not None, "--labels-output is required with pair results")
            labels = compact_fair_labels(pair_payload, plan["targets"])
            _write_jsonl(arguments.labels_output, labels)
            summary["fair_label_summary"] = summarize_pilot_labels(
                labels,
                attempted_group_count=plan["counts"]["group_count"],
                action_changed_group_count=action_changed_source_group_count(
                    pair_payload
                ),
                execution_coverage=pair_execution_coverage(
                    pair_payload, plan["targets"]
                ),
            )
            pair_rows = pair_payload.get("pairs")
            if isinstance(pair_rows, list) and any(
                isinstance(pair, Mapping) and pair.get("horizon") == "H_system"
                for pair in pair_rows
            ):
                summary["h_system_component_mean_deltas"] = (
                    summarize_h_system_component_mean_deltas(pair_payload)
                )
        _write_json(arguments.summary_output, summary)
        print(json.dumps(plan["counts"], sort_keys=True))
        return 0
    except (OSError, TypeError, json.JSONDecodeError, SourcePilotError) as exc:
        print(f"G23 Source pilot failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
