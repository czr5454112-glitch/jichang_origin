#!/usr/bin/env python3
"""Plan and reduce the fixed G23 Route-externality neighborhood study.

This runner deliberately exposes one existing local Route intervention only:
at current node 16, replace the S4 edge 17 by ``NEXT_EDGE 21`` and observe the
existing G22 ``H_system`` endpoint.  Candidate selection uses only the
alternate edge's one-hop target queue from the frozen G22 2x census.  It does
not add a planner,
model, WAIT action, H_bag replay, or online policy.

The default command is plan-only. Native execution attempts can be run later,
one explicit manifest shard at a time, with ``--run-pairs``. Applicability
guard abstentions remain attempts but are never effect labels.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf22_action_timing as g22
from scripts.eval import run_g4irsf23_precursor_route as precursor


GROUP_SCHEMA = "czr005.g4irsf23.externality_neighborhood_group.v1"
PLAN_SCHEMA = "czr005.g4irsf23.externality_neighborhood_plan.v1"
SHARD_SCHEMA = "czr005.g4irsf23.externality_neighborhood_shards.v1"
MERGED_SCHEMA = "czr005.g4irsf23.externality_neighborhood_merged_pairs.v1"
GATE_SCHEMA = "czr005.g4irsf23.externality_neighborhood_exact_gate.v1"
ACTION_SCHEMA = "czr005.g4irsf23.externality_neighborhood_action.v1"
RESULT_SCHEMA = "czr005.g4irsf23.externality_neighborhood_result.v1"
SUMMARY_SCHEMA = "czr005.g4irsf23.externality_neighborhood_summary.v1"

RESEARCH_PROFILE = g22.RESEARCH_PROFILE
CURRENT_NODE = 16
BASELINE_NEXT_NODE = 17
TREATMENT_NEXT_NODE = 21
TARGET_BLOCKS = tuple(range(22, 30))
DISCOVERY_BLOCKS = tuple(range(22, 26))
HELDOUT_BLOCKS = tuple(range(26, 30))
TARGET_GROUP_COUNT = 256
EXPECTED_HISTORICAL_H_SYSTEM_GROUPS = 67
MIN_ALT_TARGET_QUEUE = 16.0
ONE_HOP_PRESSURE_BINS = ("q16_23", "q24_31", "q32_plus")
ONE_HOP_SELECTION_SCOPE = "ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY"
DEFAULT_SHARD_GROUPS = 4
DEFAULT_MAX_WORKERS = 8

SYSTEM_GAIN_SECONDS = 0.01
SYSTEM_TAIL_TOLERANCE_SECONDS = 0.001
REQUIRED_SYSTEM_BENEFICIAL = 20
REQUIRED_FAIR_SYSTEM_BENEFICIAL_CELLS = 3
SIGNATURE_MIN_SUPPORT = 8
REQUIRED_ACTION_CHANGE_RATE = 0.80
GUARD_ABSTAIN_STATUS = "SCREENING_FALSE_POSITIVE"
GUARD_ABSTAIN_REASON = "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED"


class ExternalityNeighborhoodError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExternalityNeighborhoodError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _finite(value: Any, field: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{field} must be finite",
    )
    return float(value)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def default_historical_pair_paths(root: Path = ROOT) -> list[Path]:
    """Locate the six G22 raw pair files that contain 67 unique H_system groups."""

    roots = (
        root / "outputs" / "runtime" / "g4irsf22_action_timing",
        root / ".g4irsf22_worktree" / "outputs" / "runtime" / "g4irsf22_action_timing",
        root.parent
        / ".g4irsf22_worktree"
        / "outputs"
        / "runtime"
        / "g4irsf22_action_timing",
    )
    runtime = next(
        (
            candidate
            for candidate in roots
            if (candidate / "g4irsf22_current_hsystem64_shard0_pairs.json").is_file()
        ),
        None,
    )
    _require(runtime is not None, "could not locate the G22 H_system raw pair directory")
    paths = [
        runtime / f"g4irsf22_current_hsystem64_shard{index}_pairs.json"
        for index in range(4)
    ]
    paths.extend(
        (
            runtime / "g4irsf22_detour_gate_hsystem_pairs.json",
            runtime / "g4irsf22_positive_hsystem_pairs.json",
        )
    )
    _require(all(path.is_file() for path in paths), "a required G22 H_system pair file is missing")
    return paths


def _historical_group_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    group = row.get("population_group_id")
    selection = row.get("population_selection_id")
    ordinal = row.get("event_ordinal")
    _require(isinstance(group, str) and group, "historical pair omitted population_group_id")
    _require(
        isinstance(selection, str) and selection,
        "historical pair omitted population_selection_id",
    )
    _require(type(ordinal) is int and ordinal >= 0, "historical pair omitted event_ordinal")
    return group, selection, ordinal


def load_historical_h_system_exclusions(
    paths: Sequence[Path],
) -> tuple[set[tuple[str, str, int]], set[int], dict[str, Any]]:
    """Read only identities needed to prevent reusing earlier G22 experiments."""

    group_keys: set[tuple[str, str, int]] = set()
    runtime_bag_ids: set[int] = set()
    pair_count = 0
    for path in paths:
        payload = _read_json(path)
        _require(isinstance(payload, Mapping), f"{path} is not a pair payload")
        pairs = payload.get("pairs")
        _require(isinstance(pairs, list), f"{path} omitted pairs")
        for pair in pairs:
            if not isinstance(pair, Mapping) or pair.get("horizon") != "H_system":
                continue
            pair_count += 1
            group_keys.add(_historical_group_key(pair))
            descriptor = pair.get("resolved_execution_descriptor")
            runtime_bag_id = (
                descriptor.get("runtime_bag_id") if isinstance(descriptor, Mapping) else None
            )
            _require(
                type(runtime_bag_id) is int and runtime_bag_id >= 0,
                "historical H_system pair omitted resolved runtime_bag_id",
            )
            runtime_bag_ids.add(runtime_bag_id)
    return group_keys, runtime_bag_ids, {
        "source_file_count": len(paths),
        "h_system_pair_row_count": pair_count,
        "unique_h_system_group_count": len(group_keys),
        "unique_h_system_runtime_bag_count": len(runtime_bag_ids),
    }


def pressure_bin(target_queue: float) -> str:
    """Return the preregistered outcome-free one-hop target-queue bin."""

    queue = _finite(target_queue, "target_queue_length")
    return "q16_23" if queue < 24.0 else ("q24_31" if queue < 32.0 else "q32_plus")


def _event_group_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(row["population_group_id"]),
        str(row["population_selection_id"]),
        int(row["event_ordinal"]),
    )


def _event_order(row: Mapping[str, Any]) -> tuple[float, int, int]:
    ordinal = int(row["event_ordinal"])
    return float(row["event_time"]), int(row.get("event_seq", ordinal)), ordinal


def scan_eligible_groups(
    census_path: Path,
    *,
    historical_group_keys: set[tuple[str, str, int]],
    historical_runtime_bag_ids: set[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stream the G22 census once and retain only fixed, pre-action candidates."""

    by_cell_and_bag: dict[tuple[int, str, int], dict[str, Any]] = {}
    census_rows = 0
    fixed_route_rows = 0
    pressure_rows = 0
    historical_group_excluded = 0
    historical_bag_excluded = 0
    with census_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            census_rows += 1
            raw = json.loads(line)
            _require(isinstance(raw, Mapping), f"{census_path}:{line_number} is not an object")
            if (
                raw.get("current_node") != CURRENT_NODE
                or raw.get("baseline_next_node") != BASELINE_NEXT_NODE
                or TREATMENT_NEXT_NODE not in raw.get("candidate_next_nodes", [])
            ):
                continue
            event = g22.normalize_route_event(raw)
            block = int(float(event["event_time"]) // 900.0)
            if block not in TARGET_BLOCKS:
                continue
            fixed_route_rows += 1
            alternate_index = event["candidate_next_nodes"].index(TREATMENT_NEXT_NODE)
            alternate = event["candidate_observations"][alternate_index]
            target_queue = _finite(
                alternate.get("target_queue_length"), "alternate.target_queue_length"
            )
            if target_queue < MIN_ALT_TARGET_QUEUE:
                continue
            pressure_rows += 1
            if _event_group_key(event) in historical_group_keys:
                historical_group_excluded += 1
                continue
            runtime_bag_id = int(event["runtime_bag_id"])
            if runtime_bag_id in historical_runtime_bag_ids:
                historical_bag_excluded += 1
                continue
            bucket = pressure_bin(target_queue)
            event.update(
                {
                    "g4irsf23_schema": GROUP_SCHEMA,
                    "timing_stage": "current",
                    "time_block": block,
                    "pressure_bin": bucket,
                    "selection_cell": f"block_{block}|{bucket}",
                    "alternate_target_queue_length": target_queue,
                    "selection_scope": ONE_HOP_SELECTION_SCOPE,
                    "two_hop_queue_pressure_used_for_selection": False,
                    "experiment_action_kind": "NEXT_EDGE",
                    "experiment_selected_next_node": TREATMENT_NEXT_NODE,
                    "assigned_horizons": ["H_system"],
                    "outcome_fields_used_for_selection": False,
                    "absolute_ids_are_trace_only": True,
                }
            )
            key = (block, bucket, runtime_bag_id)
            incumbent = by_cell_and_bag.get(key)
            if incumbent is None or _event_order(event) < _event_order(incumbent):
                by_cell_and_bag[key] = event
    rows = list(by_cell_and_bag.values())
    return rows, {
        "census_row_count": census_rows,
        "fixed_route_block_row_count": fixed_route_rows,
        "one_hop_pressure_filter_row_count": pressure_rows,
        "eligible_cell_bag_count": len(rows),
        "eligible_unique_runtime_bag_count": len(
            {int(row["runtime_bag_id"]) for row in rows}
        ),
        "historical_group_row_excluded_count": historical_group_excluded,
        "historical_runtime_bag_row_excluded_count": historical_bag_excluded,
    }


def _cell_key(row: Mapping[str, Any]) -> tuple[int, str]:
    """Keep cell formation as one explicit pre-action rule."""

    return int(row["time_block"]), str(row["pressure_bin"])


def _cell_label(cell: tuple[int, str]) -> str:
    return f"block_{cell[0]}|{cell[1]}"


def select_round_robin_groups(
    candidates: Sequence[Mapping[str, Any]], *, target_count: int = TARGET_GROUP_COUNT
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Round-robin over block x pressure cells while using each bag once."""

    _require(type(target_count) is int and target_count >= 1, "target_count must be positive")
    buckets: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in candidates:
        row = dict(_plain(raw))
        buckets[_cell_key(row)].append(row)
    for rows in buckets.values():
        rows.sort(key=_event_order)
    cells = sorted(buckets)
    positions = {cell: 0 for cell in cells}
    selected: list[dict[str, Any]] = []
    used_bags: set[int] = set()
    selection_round = 0
    active = list(cells)
    while active and len(selected) < target_count:
        next_active: list[tuple[int, str]] = []
        for cell in active:
            rows = buckets[cell]
            position = positions[cell]
            while position < len(rows) and int(rows[position]["runtime_bag_id"]) in used_bags:
                position += 1
            if position < len(rows) and len(selected) < target_count:
                row = rows[position]
                position += 1
                bag = int(row["runtime_bag_id"])
                used_bags.add(bag)
                row["round_robin_selection_rank"] = len(selected)
                row["round_robin_round"] = selection_round
                selected.append(row)
            positions[cell] = position
            if any(int(row["runtime_bag_id"]) not in used_bags for row in rows[position:]):
                next_active.append(cell)
        active = next_active
        selection_round += 1

    selected.sort(key=_event_order)
    cell_audit: dict[str, Any] = {}
    for cell in cells:
        block, bucket = cell
        key = _cell_label(cell)
        cell_audit[key] = {
            "time_block": block,
            "pressure_bin": bucket,
            "available_cell_bag_count": len(buckets[cell]),
            "selected_group_count": sum(
                int(row["time_block"]) == block and row["pressure_bin"] == bucket
                for row in selected
            ),
        }
    selected_blocks = {int(row["time_block"]) for row in selected}
    complete = len(selected) == target_count and selected_blocks == set(TARGET_BLOCKS)
    return selected, {
        "status": "COMPLETE" if complete else "NO_GO_INSUFFICIENT_NEIGHBORHOOD",
        "requested_group_count": target_count,
        "selected_group_count": len(selected),
        "selected_unique_runtime_bag_count": len(used_bags),
        "selected_block_count": len(selected_blocks),
        "all_target_blocks_covered": selected_blocks == set(TARGET_BLOCKS),
        "selected_pressure_bin_count": len({str(row["pressure_bin"]) for row in selected}),
        "selected_cell_count": len(
            {_cell_key(row) for row in selected}
        ),
        "cells": cell_audit,
        "selection_order": "ROUND_ROBIN_BLOCK_X_ONE_HOP_QUEUE_THEN_EVENT_TIME",
        "outcome_fields_used": False,
    }


def build_targets(groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for group in groups:
        candidates = [
            row
            for row in g22.build_action_targets(group, horizons="H_system")
            if row.get("action_kind") == "NEXT_EDGE"
            and row.get("selected_next_node") == TREATMENT_NEXT_NODE
        ]
        _require(len(candidates) == 1, "fixed NEXT_EDGE 21 target is not uniquely legal")
        target = candidates[0]
        _require(target.get("horizon") == "H_system", "target horizon drifted")
        targets.append(target)
    _require(len({externality_target_id(row) for row in targets}) == len(targets), "duplicate targets")
    return targets


def externality_group_id(row: Mapping[str, Any]) -> str:
    group = row.get("population_group_id")
    selection = row.get("population_selection_id")
    ordinal = row.get("event_ordinal")
    _require(isinstance(group, str) and group, "target omitted population_group_id")
    _require(isinstance(selection, str) and selection, "target omitted population_selection_id")
    _require(type(ordinal) is int and ordinal >= 0, "target omitted event_ordinal")
    return f"{group}|{selection}|{ordinal}"


def externality_target_id(row: Mapping[str, Any]) -> str:
    _require(row.get("horizon") == "H_system", "externality target must use H_system")
    _require(row.get("action_kind") == "NEXT_EDGE", "externality target must be NEXT_EDGE")
    _require(
        row.get("selected_next_node") == TREATMENT_NEXT_NODE,
        "externality target must select node 21",
    )
    return f"{externality_group_id(row)}|H_system|NEXT_EDGE:{TREATMENT_NEXT_NODE}"


def build_shard_manifest(
    targets: Sequence[Mapping[str, Any]],
    *,
    shard_groups: int = DEFAULT_SHARD_GROUPS,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> dict[str, Any]:
    _require(type(shard_groups) is int and shard_groups >= 1, "shard_groups must be positive")
    _require(type(max_workers) is int and max_workers >= 1, "max_workers must be positive")
    ordered = sorted((dict(_plain(row)) for row in targets), key=_event_order)
    shards: list[dict[str, Any]] = []
    for offset in range(0, len(ordered), shard_groups):
        rows = ordered[offset : offset + shard_groups]
        shards.append(
            {
                "shard_id": f"system-{offset // shard_groups:03d}",
                "panel": "H_SYSTEM_ONLY",
                "group_count": len(rows),
                "target_count": len(rows),
                "target_ids": [externality_target_id(row) for row in rows],
                "min_event_ordinal": min(int(row["event_ordinal"]) for row in rows),
                "max_event_ordinal": max(int(row["event_ordinal"]) for row in rows),
            }
        )
    target_ids = [target_id for shard in shards for target_id in shard["target_ids"]]
    _require(len(set(target_ids)) == len(target_ids) == len(targets), "shards do not partition targets")
    return {
        "schema": SHARD_SCHEMA,
        "execution_default": "PLAN_ONLY_DO_NOT_START_PROCESSES",
        "research_profile": RESEARCH_PROFILE,
        "selection_scope": ONE_HOP_SELECTION_SCOPE,
        "one_hop_pressure_bins": list(ONE_HOP_PRESSURE_BINS),
        "two_hop_queue_pressure_used": False,
        "max_workers": max_workers,
        "partition_order": "CONTIGUOUS_EVENT_ORDINAL_KEEP_ONE_EVENT_PER_GROUP",
        "group_count": len(targets),
        "expected_execution_target_count": len(targets),
        "horizon_target_counts": {"H_bag": 0, "H_system": len(targets)},
        "action_target_counts": {"NEXT_EDGE": len(targets), "WAIT": 0},
        "shard_count": len(shards),
        "shards": shards,
    }


def select_manifest_shard(
    targets: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any], shard_id: str
) -> list[dict[str, Any]]:
    _require(manifest.get("schema") == SHARD_SCHEMA, "wrong shard manifest schema")
    shards = manifest.get("shards")
    _require(isinstance(shards, list), "manifest omitted shards")
    matches = [row for row in shards if isinstance(row, Mapping) and row.get("shard_id") == shard_id]
    _require(len(matches) == 1, f"shard id must match exactly once: {shard_id}")
    target_ids = matches[0].get("target_ids")
    _require(isinstance(target_ids, list) and target_ids, "shard omitted target_ids")
    by_id = {externality_target_id(row): dict(row) for row in targets}
    _require(len(by_id) == len(targets), "duplicate plan targets")
    _require(all(target_id in by_id for target_id in target_ids), "manifest has unknown targets")
    return [by_id[target_id] for target_id in target_ids]


def build_plan(
    census_path: Path,
    historical_pair_paths: Sequence[Path],
    *,
    target_count: int = TARGET_GROUP_COUNT,
    expected_historical_groups: int = EXPECTED_HISTORICAL_H_SYSTEM_GROUPS,
) -> dict[str, Any]:
    historical_groups, historical_bags, historical_audit = load_historical_h_system_exclusions(
        historical_pair_paths
    )
    _require(
        len(historical_groups) == expected_historical_groups,
        f"expected {expected_historical_groups} historical H_system groups, found {len(historical_groups)}",
    )
    candidates, census_audit = scan_eligible_groups(
        census_path,
        historical_group_keys=historical_groups,
        historical_runtime_bag_ids=historical_bags,
    )
    groups, selection = select_round_robin_groups(candidates, target_count=target_count)
    targets = build_targets(groups)
    selected_group_keys = {_event_group_key(row) for row in groups}
    selected_bags = {int(row["runtime_bag_id"]) for row in groups}
    historical_group_overlap = len(selected_group_keys & historical_groups)
    historical_bag_overlap = len(selected_bags & historical_bags)
    _require(historical_group_overlap == 0, "selected groups overlap historical H_system groups")
    _require(historical_bag_overlap == 0, "selected bags overlap historical H_system bags")
    counts = {
        "group_count": len(groups),
        "target_count": len(targets),
        "h_system_target_count": len(targets),
        "h_bag_target_count": 0,
        "next_edge_21_target_count": len(targets),
        "wait_target_count": 0,
        "unique_runtime_bag_count": len(selected_bags),
        "historical_group_overlap_count": historical_group_overlap,
        "historical_runtime_bag_overlap_count": historical_bag_overlap,
    }
    return {
        "schema": PLAN_SCHEMA,
        "status": selection["status"],
        "research_profile": RESEARCH_PROFILE,
        "protocol": {
            "current_node": CURRENT_NODE,
            "baseline_next_node": BASELINE_NEXT_NODE,
            "treatment_action": "NEXT_EDGE",
            "treatment_next_node": TREATMENT_NEXT_NODE,
            "horizon": "H_system",
            "time_blocks": list(TARGET_BLOCKS),
            "discovery_blocks": list(DISCOVERY_BLOCKS),
            "heldout_blocks": list(HELDOUT_BLOCKS),
            "minimum_alternate_target_queue": MIN_ALT_TARGET_QUEUE,
            "selection_scope": ONE_HOP_SELECTION_SCOPE,
            "one_hop_pressure_bins": list(ONE_HOP_PRESSURE_BINS),
            "two_hop_queue_pressure_used": False,
            "wait_planned": False,
            "h_bag_planned": False,
            "planner_or_model_added": False,
        },
        "historical_exclusions": historical_audit,
        "census_audit": census_audit,
        "selection": selection,
        "counts": counts,
        "groups": groups,
        "targets": targets,
    }


def merge_pair_payloads(
    payloads: Sequence[Mapping[str, Any]], expected_targets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    expected = {externality_target_id(row): dict(row) for row in expected_targets}
    _require(len(expected) == len(expected_targets), "duplicate expected target identity")
    merged: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for index, payload in enumerate(payloads):
        pairs = payload.get("pairs")
        _require(isinstance(pairs, list), f"pair payload {index} omitted pairs")
        for pair in pairs:
            _require(isinstance(pair, Mapping), "pair payload contains a non-object")
            pair_id = externality_target_id(pair)
            _require(pair_id in expected, f"unexpected native pair: {pair_id}")
            plain = dict(_plain(pair))
            incumbent = merged.get(pair_id)
            if incumbent is not None:
                _require(incumbent == plain, f"conflicting duplicate native pair: {pair_id}")
                duplicate_count += 1
            else:
                merged[pair_id] = plain
    missing = [target_id for target_id in expected if target_id not in merged]
    return {
        "schema": MERGED_SCHEMA,
        "pairs": [merged[target_id] for target_id in expected if target_id in merged],
        "input_payload_count": len(payloads),
        "duplicate_pair_count": duplicate_count,
        "expected_target_count": len(expected),
        "observed_target_count": len(merged),
        "missing_target_count": len(missing),
        "missing_target_ids": missing,
        "coverage_complete": not missing,
    }


def _exact_pair_reasons(pair: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    checks = (
        (pair.get("pair_status") == "ACTION_CHANGED_HORIZON_COMPLETE", "PAIR_STATUS"),
        (pair.get("same_state_start") is True, "SAME_STATE_START"),
        (pair.get("action_changed") is True, "ACTION_CHANGED"),
        (pair.get("pair_complete") is True, "PAIR_COMPLETE"),
        (pair.get("horizon_complete", True) is True, "HORIZON_COMPLETE"),
        (pair.get("live_safety_pass") is True, "LIVE_SAFETY"),
        (pair.get("hard_gate_pass") is True, "HARD_GATE"),
        (pair.get("formal_hard_gate_evaluated") is True, "FORMAL_EVALUATED"),
        (pair.get("formal_hard_gate_pass") is True, "FORMAL_PASS"),
    )
    reasons.extend(name for passed, name in checks if not passed)
    certificate = pair.get("committed_action_certificate")
    if not isinstance(certificate, Mapping):
        reasons.append("ACTION_CERTIFICATE")
    else:
        certificate_checks = (
            certificate.get("valid") is True,
            certificate.get("changed_action_count") == 1,
            certificate.get("pre_action_snapshots_match") is True,
            certificate.get("post_commit_verified") is True,
        )
        if not all(certificate_checks):
            reasons.append("ACTION_CERTIFICATE")
    affected = pair.get("affected_bag_deltas")
    if not isinstance(affected, list) or not affected:
        reasons.append("AFFECTED_BAG_COMPLETION")
    descriptor = pair.get("resolved_execution_descriptor")
    if isinstance(descriptor, Mapping):
        if descriptor.get("node") != CURRENT_NODE:
            reasons.append("RESOLVED_CURRENT_NODE")
        if descriptor.get("baseline_next_node") != BASELINE_NEXT_NODE:
            reasons.append("RESOLVED_BASELINE_EDGE")
        if descriptor.get("selected_next_node") != TREATMENT_NEXT_NODE:
            reasons.append("RESOLVED_TREATMENT_EDGE")
    return reasons


def _guard_abstain_reason(pair: Mapping[str, Any]) -> str | None:
    """Recognize the native seam's explicit, completed applicability abstention."""

    if pair.get("pair_status") != GUARD_ABSTAIN_STATUS:
        return None
    reason = pair.get("false_positive_reason")
    certificate = pair.get("committed_action_certificate")
    certificate_reason = (
        certificate.get("application_reason")
        if isinstance(certificate, Mapping)
        else None
    )
    if (
        reason == GUARD_ABSTAIN_REASON
        and certificate_reason == GUARD_ABSTAIN_REASON
        and pair.get("same_state_start") is True
        and pair.get("action_changed") is not True
    ):
        return GUARD_ABSTAIN_REASON
    return None


def exact_pair_gate(
    payload: Mapping[str, Any],
    expected_targets: Sequence[Mapping[str, Any]],
    *,
    required_action_change_rate: float = REQUIRED_ACTION_CHANGE_RATE,
) -> dict[str, Any]:
    """Audit identity coverage, recognized outcomes, and applicability separately.

    A native guard abstention is a completed execution outcome, but it is not an
    action-changing certificate and contributes no effect or fairness label.
    """

    merged = merge_pair_payloads([payload], expected_targets)
    applied: list[Mapping[str, Any]] = []
    abstentions: list[tuple[Mapping[str, Any], str]] = []
    failures: list[dict[str, Any]] = []
    for pair in merged["pairs"]:
        reasons = _exact_pair_reasons(pair)
        if not reasons:
            applied.append(pair)
            continue
        abstain_reason = _guard_abstain_reason(pair)
        if abstain_reason is not None:
            abstentions.append((pair, abstain_reason))
            continue
        failures.append(
            {"target_id": externality_target_id(pair), "reasons": reasons}
        )
    expected_count = merged["expected_target_count"]
    attempted_count = merged["observed_target_count"]
    action_change_rate = len(applied) / expected_count if expected_count else 0.0
    execution_coverage_pass = (
        merged["coverage_complete"]
        and attempted_count == expected_count
        and merged["missing_target_count"] == 0
    )
    recognized_outcomes_pass = not failures
    action_change_rate_pass = action_change_rate >= required_action_change_rate
    passed = (
        execution_coverage_pass
        and recognized_outcomes_pass
        and action_change_rate_pass
    )
    abstain_reasons = Counter(reason for _, reason in abstentions)
    return {
        "schema": GATE_SCHEMA,
        "status": (
            "PASS_EXECUTION_COVERAGE_AND_ACTION_CHANGE_GATE"
            if passed
            else "NO_GO_EXECUTION_COVERAGE_OR_ACTION_CHANGE_GATE"
        ),
        "pass": passed,
        "execution_coverage_pass": execution_coverage_pass,
        "recognized_execution_outcomes_pass": recognized_outcomes_pass,
        "action_changing_rate_pass": action_change_rate_pass,
        "expected_target_count": merged["expected_target_count"],
        "attempted_target_count": attempted_count,
        "execution_coverage_count": attempted_count,
        "missing_target_count": merged["missing_target_count"],
        "unknown_target_count": 0,
        "action_applied_count": len(applied),
        "guard_abstain_count": len(abstentions),
        "action_changing_rate": action_change_rate,
        "required_action_change_rate": required_action_change_rate,
        "guard_abstain_reasons": dict(sorted(abstain_reasons.items())),
        "failure_count": len(failures),
        "failures": failures,
    }


def _cohort_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["raw_bag_mean_delta_seconds"]) for row in rows]
    beneficial = sum(row["system_beneficial"] is True for row in rows)
    fair_beneficial = sum(
        row.get("fair_system_beneficial") is True for row in rows
    )
    return {
        "support": len(rows),
        "system_beneficial_count": beneficial,
        "system_beneficial_rate": beneficial / len(rows) if rows else 0.0,
        "fair_system_beneficial_count": fair_beneficial,
        "fair_system_beneficial_rate": (
            fair_beneficial / len(rows) if rows else 0.0
        ),
        "mean_delta_seconds": statistics.fmean(deltas) if deltas else None,
        "median_delta_seconds": statistics.median(deltas) if deltas else None,
    }


def heldout_local_signature(
    action_rows: Sequence[Mapping[str, Any]], *, min_support: int = SIGNATURE_MIN_SUPPORT
) -> dict[str, Any]:
    """Choose one target-queue bin on blocks 22-25, then hold out 26-29."""

    complete = [
        row for row in action_rows if row.get("effect_evidence_complete") is True
    ]
    bins = sorted({str(row["pressure_bin"]) for row in complete})
    diagnostics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for bucket in bins:
        discovery = [
            row
            for row in complete
            if row["pressure_bin"] == bucket and int(row["time_block"]) in DISCOVERY_BLOCKS
        ]
        heldout = [
            row
            for row in complete
            if row["pressure_bin"] == bucket and int(row["time_block"]) in HELDOUT_BLOCKS
        ]
        discovery_summary = _cohort_summary(discovery)
        heldout_summary = _cohort_summary(heldout)
        support_eligible = (
            discovery_summary["support"] >= min_support
            and heldout_summary["support"] >= min_support
        )
        discovery_has_benefit = discovery_summary["system_beneficial_count"] >= 1
        row = {
            "pressure_bin": bucket,
            "discovery": discovery_summary,
            "heldout": heldout_summary,
            "support_eligible": support_eligible,
            "discovery_has_system_benefit": discovery_has_benefit,
        }
        diagnostics.append(row)
        if support_eligible and discovery_has_benefit:
            candidates.append(row)
    selected = min(
        candidates,
        key=lambda row: (
            -float(row["discovery"]["system_beneficial_rate"]),
            -int(row["discovery"]["system_beneficial_count"]),
            float(row["discovery"]["mean_delta_seconds"]),
            str(row["pressure_bin"]),
        ),
        default=None,
    )
    heldout_pass = bool(
        selected
        and selected["heldout"]["system_beneficial_count"] >= 1
        and selected["heldout"]["mean_delta_seconds"] < 0.0
        and selected["heldout"]["median_delta_seconds"] < 0.0
    )
    return {
        "feature": "one_hop_target_queue_bin",
        "discovery_blocks": list(DISCOVERY_BLOCKS),
        "heldout_blocks": list(HELDOUT_BLOCKS),
        "minimum_support_per_split": min_support,
        "selection_rule": "MAX_DISCOVERY_SYSTEM_BENEFICIAL_RATE_THEN_COUNT_THEN_MEAN",
        "selected_pressure_bin": selected["pressure_bin"] if selected else None,
        "selected_discovery": selected["discovery"] if selected else None,
        "selected_heldout": selected["heldout"] if selected else None,
        "pass": heldout_pass,
        "diagnostics": diagnostics,
        "system_benefit_scope": "SYSTEM_BENEFICIAL_ONLY",
        "individual_fairness_used": False,
        "individual_fairness_claimed": False,
    }


def compact_externality_neighborhood(
    merged_pairs: Mapping[str, Any],
    groups: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
    *,
    required_group_count: int = TARGET_GROUP_COUNT,
    required_system_beneficial: int = REQUIRED_SYSTEM_BENEFICIAL,
    required_fair_beneficial_cells: int = REQUIRED_FAIR_SYSTEM_BENEFICIAL_CELLS,
    signature_min_support: int = SIGNATURE_MIN_SUPPORT,
    required_action_change_rate: float = REQUIRED_ACTION_CHANGE_RATE,
) -> dict[str, Any]:
    pairs = merged_pairs.get("pairs")
    _require(isinstance(pairs, list), "merged payload omitted pairs")
    pair_by_id = {externality_target_id(row): row for row in pairs if isinstance(row, Mapping)}
    _require(len(pair_by_id) == len(pairs), "duplicate compact pair identity")
    group_by_id = {externality_group_id(row): row for row in groups}
    _require(len(group_by_id) == len(groups), "duplicate compact group identity")

    action_rows: list[dict[str, Any]] = []
    for target in targets:
        target_id = externality_target_id(target)
        group_id = externality_group_id(target)
        _require(group_id in group_by_id, f"target has no group: {group_id}")
        group = group_by_id[group_id]
        pair = pair_by_id.get(target_id)
        headroom_audit = precursor._deadline_headroom_audit(group)
        base = {
            "schema": ACTION_SCHEMA,
            "group_id": group_id,
            "target_id": target_id,
            "event_ordinal": int(group["event_ordinal"]),
            "runtime_bag_id": int(group["runtime_bag_id"]),
            "time_block": int(group["time_block"]),
            "pressure_bin": str(group["pressure_bin"]),
            "selection_cell": _cell_label(_cell_key(group)),
            "action_kind": "NEXT_EDGE",
            "selected_next_node": TREATMENT_NEXT_NODE,
            "horizon": "H_system",
            **headroom_audit,
        }
        exact_reasons = _exact_pair_reasons(pair) if pair is not None else ["PAIR_MISSING"]
        abstain_reason = _guard_abstain_reason(pair) if pair is not None else None
        if pair is None or exact_reasons:
            is_guard_abstain = abstain_reason is not None
            action_rows.append(
                {
                    **base,
                    "execution_observed": pair is not None,
                    "execution_status": pair.get("pair_status") if pair is not None else None,
                    "action_applied": False,
                    "guard_abstain": is_guard_abstain,
                    "guard_abstain_reason": abstain_reason,
                    "effect_evidence_complete": False,
                    "system_safe": False,
                    "system_beneficial": False,
                    "individual_direct_cost_seconds": None,
                    "individual_direct_nonregressing": None,
                    "individual_direct_beneficial": None,
                    **precursor._treatment_current_bag_audit({}),
                    "individual_fair_evidence_complete": False,
                    "individual_cost_within_headroom": False,
                    "individual_fair": False,
                    "strict_no_delay": False,
                    "fair_system_beneficial": False,
                    "system_beneficial_but_costly": False,
                    "system_beneficial_but_unfair": False,
                    "benefit_fairness_label": (
                        "NATIVE_GUARD_ABSTAIN"
                        if is_guard_abstain
                        else "PAIR_MISSING_OR_INEXACT"
                    ),
                    "raw_bag_mean_delta_seconds": None,
                    "raw_bag_p95_delta_seconds": None,
                    "raw_bag_p99_delta_seconds": None,
                    "raw_bag_max_delta_seconds": None,
                    "deadline_miss_delta": None,
                }
            )
            continue
        metrics = precursor._raw_bag_metrics(pair)
        direct_cost = precursor._direct_completion_delta(pair)
        p95_p99_safe = all(
            metrics[name] <= SYSTEM_TAIL_TOLERANCE_SECONDS
            for name in (
                "raw_bag_p95_delta_seconds",
                "raw_bag_p99_delta_seconds",
            )
        )
        deadline_safe = metrics["deadline_miss_delta"] <= 0
        system_safe = (
            metrics["raw_bag_comparison_eligible"] is True
            and p95_p99_safe
            and deadline_safe
        )
        system_beneficial = (
            system_safe
            and metrics["raw_bag_mean_delta_seconds"] <= -SYSTEM_GAIN_SECONDS
        )
        treatment_audit = precursor._treatment_current_bag_audit(pair)
        strict_no_delay = direct_cost <= SYSTEM_TAIL_TOLERANCE_SECONDS
        individual_fair_evidence_complete = all(
            value is True
            for value in (
                headroom_audit["deadline_headroom_evidence_complete"],
                treatment_audit["treatment_current_bag_evidence_complete"],
            )
        )
        headroom = headroom_audit["deadline_headroom_seconds"]
        individual_cost_within_headroom = (
            individual_fair_evidence_complete
            and isinstance(headroom, (int, float))
            and direct_cost <= float(headroom)
        )
        individual_fair = all(
            value is True
            for value in (
                individual_fair_evidence_complete,
                individual_cost_within_headroom,
                treatment_audit["treatment_current_bag_completed"],
                treatment_audit["treatment_current_bag_failed"] is False,
                treatment_audit["treatment_current_bag_before_deadline"],
                deadline_safe,
            )
        )
        fair_system_beneficial = system_beneficial and individual_fair
        action_rows.append(
            {
                **base,
                "execution_observed": True,
                "execution_status": str(pair["pair_status"]),
                "action_applied": True,
                "guard_abstain": False,
                "guard_abstain_reason": None,
                "effect_evidence_complete": True,
                "system_safe": system_safe,
                "system_beneficial": system_beneficial,
                "individual_direct_cost_seconds": direct_cost,
                "individual_direct_nonregressing": (
                    direct_cost <= SYSTEM_TAIL_TOLERANCE_SECONDS
                ),
                "individual_direct_beneficial": direct_cost < -SYSTEM_TAIL_TOLERANCE_SECONDS,
                **treatment_audit,
                "individual_fair_evidence_complete": individual_fair_evidence_complete,
                "individual_cost_within_headroom": individual_cost_within_headroom,
                "individual_fair": individual_fair,
                "strict_no_delay": strict_no_delay,
                "fair_system_beneficial": fair_system_beneficial,
                "system_beneficial_but_costly": (
                    system_beneficial and not strict_no_delay
                ),
                "system_beneficial_but_unfair": (
                    system_beneficial and not individual_fair
                ),
                "benefit_fairness_label": precursor._benefit_fairness_label(
                    system_beneficial=system_beneficial,
                    individual_fair=individual_fair,
                    strict_no_delay=strict_no_delay,
                    individual_fair_evidence_complete=individual_fair_evidence_complete,
                    individual_cost_within_headroom=individual_cost_within_headroom,
                ),
                **metrics,
            }
        )

    execution_coverage_count = sum(row["execution_observed"] for row in action_rows)
    applied_count = sum(row["action_applied"] for row in action_rows)
    abstain_count = sum(row["guard_abstain"] for row in action_rows)
    unexpected_outcome_count = sum(
        row["execution_observed"] is True
        and row["action_applied"] is False
        and row["guard_abstain"] is False
        for row in action_rows
    )
    effect_complete_count = sum(
        row["effect_evidence_complete"] for row in action_rows
    )
    action_change_rate = applied_count / len(action_rows) if action_rows else 0.0
    abstain_reasons = Counter(
        str(row["guard_abstain_reason"])
        for row in action_rows
        if row["guard_abstain"] is True
    )
    safe_count = sum(row["system_safe"] for row in action_rows)
    beneficial = [row for row in action_rows if row["system_beneficial"]]
    fair_beneficial = [row for row in action_rows if row["fair_system_beneficial"]]
    beneficial_costly = [
        row for row in action_rows if row["system_beneficial_but_costly"]
    ]
    beneficial_unfair = [
        row for row in action_rows if row["system_beneficial_but_unfair"]
    ]
    beneficial_cells = {str(row["selection_cell"]) for row in beneficial}
    fair_beneficial_cells = {
        str(row["selection_cell"]) for row in fair_beneficial
    }
    raw_bag_max_deltas = [
        float(row["raw_bag_max_delta_seconds"])
        for row in action_rows
        if row["effect_evidence_complete"] is True
    ]
    raw_bag_max_diagnostic = {
        "role": "DIAGNOSTIC_ONLY_NOT_A_SYSTEM_HARD_GATE",
        "count": len(raw_bag_max_deltas),
        "min": min(raw_bag_max_deltas) if raw_bag_max_deltas else None,
        "mean": statistics.fmean(raw_bag_max_deltas) if raw_bag_max_deltas else None,
        "median": statistics.median(raw_bag_max_deltas) if raw_bag_max_deltas else None,
        "max": max(raw_bag_max_deltas) if raw_bag_max_deltas else None,
    }
    signature = heldout_local_signature(action_rows, min_support=signature_min_support)
    gates = {
        "execution_coverage": (
            len(action_rows) == required_group_count
            and execution_coverage_count == required_group_count
        ),
        "recognized_execution_outcomes": unexpected_outcome_count == 0,
        "action_changing_rate": action_change_rate >= required_action_change_rate,
        "fair_system_beneficial_count": (
            len(fair_beneficial) >= required_system_beneficial
        ),
        "fair_system_beneficial_block_pressure_cell_count": (
            len(fair_beneficial_cells) >= required_fair_beneficial_cells
        ),
        "heldout_local_signature": signature["pass"] is True,
    }
    continuation = all(gates.values())
    summary = {
        "schema": SUMMARY_SCHEMA,
        "status": (
            "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
            if continuation
            else "NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
        ),
        "planned_group_count": len(groups),
        "action_row_count": len(action_rows),
        "attempted_group_count": len(action_rows),
        "execution_coverage_count": execution_coverage_count,
        "missing_execution_count": len(action_rows) - execution_coverage_count,
        "unknown_execution_count": 0,
        "action_applied_count": applied_count,
        "guard_abstain_count": abstain_count,
        "action_changing_rate": action_change_rate,
        "guard_abstain_reasons": dict(sorted(abstain_reasons.items())),
        "unexpected_execution_outcome_count": unexpected_outcome_count,
        "effect_complete_count": effect_complete_count,
        "system_safe_count": safe_count,
        "system_beneficial_count": len(beneficial),
        "system_beneficial_cell_count": len(beneficial_cells),
        "fair_system_beneficial_count": len(fair_beneficial),
        "fair_system_beneficial_cell_count": len(fair_beneficial_cells),
        "system_beneficial_but_costly_count": len(beneficial_costly),
        "system_beneficial_but_unfair_count": len(beneficial_unfair),
        "individual_fair_count": sum(
            row["individual_fair"] is True for row in action_rows
        ),
        "individual_fair_evidence_incomplete_count": sum(
            row["action_applied"] is True
            and row["individual_fair_evidence_complete"] is not True
            for row in action_rows
        ),
        "individual_direct_beneficial_count": sum(
            row["individual_direct_beneficial"] is True for row in action_rows
        ),
        "individual_direct_nonregressing_count": sum(
            row["individual_direct_nonregressing"] is True for row in action_rows
        ),
        "thresholds": {
            "required_group_count": required_group_count,
            "required_action_change_rate": required_action_change_rate,
            "system_mean_delta_seconds_max": -SYSTEM_GAIN_SECONDS,
            "system_p95_p99_delta_seconds_max": SYSTEM_TAIL_TOLERANCE_SECONDS,
            "deadline_miss_delta_max": 0,
            "required_fair_system_beneficial": required_system_beneficial,
            "required_fair_system_beneficial_block_pressure_cells": (
                required_fair_beneficial_cells
            ),
            "signature_min_support_per_split": signature_min_support,
        },
        "gates": gates,
        "system_tail_hard_gate_metrics": [
            "raw_bag_p95_delta_seconds",
            "raw_bag_p99_delta_seconds",
        ],
        "raw_bag_max_delta_is_diagnostic_only": True,
        "raw_bag_max_delta_seconds_diagnostic": raw_bag_max_diagnostic,
        "selection_scope": ONE_HOP_SELECTION_SCOPE,
        "one_hop_pressure_bins": list(ONE_HOP_PRESSURE_BINS),
        "two_hop_queue_pressure_used": False,
        "heldout_local_signature": signature,
        "continuation_pass": continuation,
        "execution_coverage_and_effect_evidence_are_separate": True,
        "effect_and_fairness_use_action_applied_pairs_only": True,
        "guard_abstain_is_completed_applicability_evidence": True,
        "system_safe_and_individual_cost_are_separate": True,
        "system_beneficial_and_individual_fair_are_orthogonal": True,
        "continuation_cell_coverage_uses_fair_system_beneficial": True,
        "individual_fairness_evaluated": True,
        "individual_fairness_contract": "FROZEN_PRE_ACTION_DEADLINE_HEADROOM_AND_TREATMENT_CURRENT_BAG_OUTCOME",
        "post_hoc_individual_cost_cap_applied": False,
    }
    return {"schema": RESULT_SCHEMA, "summary": summary, "actions": action_rows}


def write_action_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "group_id",
        "event_ordinal",
        "runtime_bag_id",
        "time_block",
        "pressure_bin",
        "execution_observed",
        "execution_status",
        "action_applied",
        "guard_abstain",
        "guard_abstain_reason",
        "effect_evidence_complete",
        "system_safe",
        "system_beneficial",
        "fair_system_beneficial",
        "system_beneficial_but_costly",
        "system_beneficial_but_unfair",
        "benefit_fairness_label",
        "raw_bag_mean_delta_seconds",
        "raw_bag_p95_delta_seconds",
        "raw_bag_p99_delta_seconds",
        "raw_bag_max_delta_seconds",
        "deadline_miss_delta",
        "individual_direct_cost_seconds",
        "individual_direct_nonregressing",
        "individual_direct_beneficial",
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
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_report(summary: Mapping[str, Any]) -> str:
    signature = summary["heldout_local_signature"]
    selected = signature.get("selected_pressure_bin") or "none"
    gates = summary["gates"]
    max_diagnostic = summary["raw_bag_max_delta_seconds_diagnostic"]
    return "\n".join(
        (
            "# G4IRSF23 externality neighborhood",
            "",
            f"Status: `{summary['status']}`.",
            "",
            "The preregistered intervention is only `node 16: S4 17 -> NEXT_EDGE 21` "
            "under `G22_S4_J2_E2`, evaluated at `H_system`. Selection used alternate "
            "one-hop target queue >= 16 in blocks 22-29, binned as q16_23, "
            "q24_31, and q32_plus. No WAIT, "
            "H_bag, planner, or learned model was added.",
            "",
            "System benefit and individual fairness are orthogonal. Individual fairness "
            "reuses the frozen precursor contract: pre-action deadline headroom plus a "
            "completed, non-failed treatment current bag finishing by its deadline. No "
            "post-hoc direct-cost cap is applied.",
            "",
            "The 256-group panel is an outcome-free execution panel. A native "
            "`SCREENING_FALSE_POSITIVE / NOT_APPLICABLE_ACTION_PRECONDITION_FAILED` "
            "is reported as a completed guard abstention, not as an action-changing "
            "certificate. Effect, fairness, and held-out calculations use applied "
            "action-changing pairs only.",
            "",
            "| Item | Value |",
            "|---|---:|",
            f"| Attempted H_system groups | {summary['attempted_group_count']} |",
            f"| Identity-covered executions | {summary['execution_coverage_count']} |",
            f"| Missing / unknown executions | {summary['missing_execution_count']} / {summary['unknown_execution_count']} |",
            f"| Applied action-changing groups | {summary['action_applied_count']} |",
            f"| Native guard abstentions | {summary['guard_abstain_count']} |",
            f"| Action-changing rate | {summary['action_changing_rate']:.6f} |",
            f"| Guard-abstain reasons | `{json.dumps(summary['guard_abstain_reasons'], sort_keys=True)}` |",
            f"| Effect-complete applied groups | {summary['effect_complete_count']} |",
            f"| System-safe groups | {summary['system_safe_count']} |",
            f"| System-beneficial groups | {summary['system_beneficial_count']} |",
            f"| System-beneficial block x one-hop queue cells (fairness not required) | {summary['system_beneficial_cell_count']} |",
            f"| Fair system-beneficial groups | {summary['fair_system_beneficial_count']} |",
            f"| Fair system-beneficial block x one-hop queue cells (continuation coverage) | {summary['fair_system_beneficial_cell_count']} |",
            f"| System-beneficial but costly groups | {summary['system_beneficial_but_costly_count']} |",
            f"| System-beneficial but unfair groups | {summary['system_beneficial_but_unfair_count']} |",
            f"| Selected discovery pressure bin | `{selected}` |",
            f"| Held-out local signature | {signature['pass']} |",
            f"| Raw-bag max delta, diagnostic only (count/min/mean/median/max s) | {max_diagnostic['count']} / {max_diagnostic['min']} / {max_diagnostic['mean']} / {max_diagnostic['median']} / {max_diagnostic['max']} |",
            "",
            "| Continuation gate | Pass |",
            "|---|---:|",
            f"| 256/256 execution identity coverage | {gates['execution_coverage']} |",
            f"| All execution outcomes recognized | {gates['recognized_execution_outcomes']} |",
            f"| Action-changing rate >= 0.80 | {gates['action_changing_rate']} |",
            f"| At least 20 fair system-beneficial actions | {gates['fair_system_beneficial_count']} |",
            f"| At least 3 fair system-beneficial block x one-hop queue cells | {gates['fair_system_beneficial_block_pressure_cell_count']} |",
            f"| System-only discovery 22-25 -> held-out 26-29 signature | {gates['heldout_local_signature']} |",
            "",
            "The held-out signature is preregistered on system benefit only; it does "
            "not use or claim individual-fairness replication. Fair cell coverage is "
            "a separate continuation gate. The system tail hard gate uses p95/p99 "
            "only; raw-bag max delta remains a reported diagnostic and cannot change "
            "system-safe, system-beneficial, or continuation status.",
            "",
        )
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-census", type=Path, required=True)
    parser.add_argument(
        "--historical-pair-result",
        type=Path,
        action="append",
        default=[],
        help="Override the default six G22 H_system raw pair files.",
    )
    parser.add_argument("--groups-output", type=Path, required=True)
    parser.add_argument("--targets-output", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path, required=True)
    parser.add_argument("--shard-manifest-output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--run-pairs", action="store_true")
    parser.add_argument("--pair-shard-manifest", type=Path)
    parser.add_argument("--pair-shard-id")
    parser.add_argument("--pairs-output", type=Path)
    parser.add_argument("--pair-result", type=Path, action="append", default=[])
    parser.add_argument("--merged-pairs-output", type=Path)
    parser.add_argument("--gate-output", type=Path)
    parser.add_argument("--compact-output", type=Path)
    parser.add_argument("--compact-actions-output", type=Path)
    parser.add_argument("--report-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        history = (
            arguments.historical_pair_result
            if arguments.historical_pair_result
            else default_historical_pair_paths(ROOT)
        )
        plan = build_plan(arguments.route_census, history)
        manifest = build_shard_manifest(plan["targets"])
        _write_jsonl(arguments.groups_output, plan["groups"])
        _write_jsonl(arguments.targets_output, plan["targets"])
        _write_json(
            arguments.plan_output,
            {key: value for key, value in plan.items() if key not in {"groups", "targets"}},
        )
        _write_json(arguments.shard_manifest_output, manifest)

        has_shard_manifest = arguments.pair_shard_manifest is not None
        has_shard_id = arguments.pair_shard_id is not None
        _require(
            has_shard_manifest == has_shard_id,
            "--pair-shard-manifest and --pair-shard-id must appear together",
        )
        _require(not arguments.run_pairs or arguments.binary is not None, "--run-pairs requires --binary")
        _require(not arguments.run_pairs or has_shard_manifest, "--run-pairs requires a shard")
        _require(
            not arguments.run_pairs or arguments.pairs_output is not None,
            "--run-pairs requires --pairs-output",
        )
        if arguments.run_pairs:
            loaded_manifest = _read_json(arguments.pair_shard_manifest)
            _require(isinstance(loaded_manifest, Mapping), "pair manifest must be an object")
            selected_targets = select_manifest_shard(
                plan["targets"], loaded_manifest, arguments.pair_shard_id
            )
            backend = g22.load_native_backend(arguments.binary)
            native_arguments, _, _ = g22.build_2x_native_arguments(ROOT)
            payload = g22.run_native_action_pairs(backend, native_arguments, selected_targets)
            payload["g4irsf23_externality_shard_id"] = arguments.pair_shard_id
            _write_json(arguments.pairs_output, payload)

        execution_gate_pass: bool | None = None
        if arguments.pair_result:
            payloads = [_read_json(path) for path in arguments.pair_result]
            _require(all(isinstance(row, Mapping) for row in payloads), "invalid pair payload")
            merged = merge_pair_payloads(payloads, plan["targets"])
            gate = exact_pair_gate(merged, plan["targets"])
            compact = compact_externality_neighborhood(merged, plan["groups"], plan["targets"])
            for path, name in (
                (arguments.merged_pairs_output, "--merged-pairs-output"),
                (arguments.gate_output, "--gate-output"),
                (arguments.compact_output, "--compact-output"),
                (arguments.compact_actions_output, "--compact-actions-output"),
                (arguments.report_output, "--report-output"),
            ):
                _require(path is not None, f"--pair-result requires {name}")
            _write_json(arguments.merged_pairs_output, merged)
            _write_json(arguments.gate_output, gate)
            _write_json(arguments.compact_output, compact)
            write_action_csv(arguments.compact_actions_output, compact["actions"])
            arguments.report_output.parent.mkdir(parents=True, exist_ok=True)
            arguments.report_output.write_text(
                render_report(compact["summary"]), encoding="utf-8"
            )
            execution_gate_pass = gate["pass"] is True

        print(
            json.dumps(
                {
                    "status": plan["status"],
                    **plan["counts"],
                    "shard_count": manifest["shard_count"],
                },
                sort_keys=True,
            )
        )
        if plan["status"] != "COMPLETE" or execution_gate_pass is False:
            return 2
        return 0
    except (
        OSError,
        TypeError,
        json.JSONDecodeError,
        g22.ActionTimingError,
        precursor.PrecursorRouteError,
        ExternalityNeighborhoodError,
    ) as exc:
        print(f"G23 externality neighborhood failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
