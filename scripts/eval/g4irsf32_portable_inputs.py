#!/usr/bin/env python3
"""Normalized workload and fault inputs for a pre-registered unseen map.

This module translates explicit external node IDs into the dense IDs already
validated by ``g4irsf31_map_adapter``.  It deliberately does not infer roles,
project an airport timetable, select an EBS proxy, or choose fault edges.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from scripts.eval import g4irsf31_map_adapter as map_adapter


PORTABLE_WORKLOAD_SCHEMA = "czr005.g4irsf32.portable_workload.v1"
PORTABLE_FAULT_SCHEMA = "czr005.g4irsf32.portable_fault_scenarios.v1"


class PortableInputError(ValueError):
    """Raised when a normalized workload or fault input is not runnable."""


@dataclass(frozen=True)
class PortableWorkload:
    source_path: Path
    map_id: str
    storage_pair_id: str | None
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PortableFaultScenario:
    scenario_id: str
    fault_windows: tuple[tuple[int, int, float, float, float, bool], ...]


def _read_object(path: str | Path, label: str) -> tuple[Path, Mapping[str, Any]]:
    resolved = Path(path).resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortableInputError(f"cannot load {label} {resolved}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise PortableInputError(f"{label} root must be an object")
    return resolved, payload


def _portable_profile(
    profile: map_adapter.RuntimeMapProfile,
) -> dict[str, int]:
    if (
        profile.schema != map_adapter.PORTABLE_MAP_SCHEMA
        or not profile.explicit_roles
    ):
        raise PortableInputError("portable inputs require an explicit-role profile")
    if len(profile.external_node_ids) != len(profile.node_records):
        raise PortableInputError("portable profile external-ID mapping is incomplete")
    return {
        external: dense
        for dense, external in enumerate(profile.external_node_ids)
    }


def _external_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PortableInputError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PortableInputError(f"{label} must be an integer")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortableInputError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PortableInputError(f"{label} must be finite")
    return result


def _is_reachable(
    adjacency: Mapping[int, tuple[int, ...]],
    start: int,
    goal: int,
) -> bool:
    pending = [start]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if current == goal:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency[current])
    return False


def load_portable_workload(
    manifest_path: str | Path,
    profile: map_adapter.RuntimeMapProfile,
) -> PortableWorkload:
    """Load canonical JSONL segments and validate their explicit map roles."""

    external_to_dense = _portable_profile(profile)
    path, manifest = _read_object(manifest_path, "portable workload manifest")
    if manifest.get("schema") != PORTABLE_WORKLOAD_SCHEMA:
        raise PortableInputError("unsupported portable workload schema")
    if manifest.get("map_id") != profile.map_id:
        raise PortableInputError("portable workload map_id does not match profile")

    segment_count = _integer(manifest.get("segment_count"), "segment_count")
    if segment_count <= 0:
        raise PortableInputError("segment_count must be positive")
    segments_value = manifest.get("segments_path")
    if not isinstance(segments_value, str) or not segments_value:
        raise PortableInputError("segments_path must be a non-empty string")
    segments_path = Path(segments_value)
    if not segments_path.is_absolute():
        segments_path = path.parent / segments_path

    pair_id_value = manifest.get("storage_pair_id")
    if pair_id_value is not None and not isinstance(pair_id_value, str):
        raise PortableInputError("storage_pair_id must be a string or null")
    storage_pair_id = pair_id_value
    pair_by_id = {pair.pair_id: pair for pair in profile.storage_pairs}
    if profile.storage_mode == "none" and storage_pair_id is not None:
        raise PortableInputError("storage mode 'none' cannot select an EBS pair")
    selected_pair = (
        pair_by_id.get(storage_pair_id) if storage_pair_id is not None else None
    )
    if storage_pair_id is not None and selected_pair is None:
        raise PortableInputError(f"unknown storage_pair_id: {storage_pair_id}")

    rows: list[dict[str, Any]] = []
    segment_ids: set[str] = set()
    adjacency = {
        int(row[0]): tuple(int(value) for value in row[5])
        for row in profile.node_records
    }
    reachability: dict[tuple[int, int], bool] = {}
    try:
        handle = segments_path.open(encoding="utf-8")
    except OSError as exc:
        raise PortableInputError(
            f"cannot load portable workload rows {segments_path}: {exc}"
        ) from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PortableInputError(
                    f"segments line {line_number} is not valid JSON: {exc}"
                ) from exc
            if not isinstance(raw, Mapping):
                raise PortableInputError(
                    f"segments line {line_number} must be an object"
                )
            segment_id = _external_id(
                raw.get("segment_id"), f"segments[{line_number}].segment_id"
            )
            if segment_id in segment_ids:
                raise PortableInputError(f"duplicate segment_id: {segment_id}")
            segment_ids.add(segment_id)
            task_id = _integer(
                raw.get("task_id"), f"segments[{line_number}].task_id"
            )
            release = _finite(
                raw.get("pass_time"), f"segments[{line_number}].pass_time"
            )
            deadline = _finite(
                raw.get("std"), f"segments[{line_number}].std"
            )
            if release > deadline:
                raise PortableInputError(
                    f"segments[{line_number}] pass_time exceeds std"
                )
            start_external = _external_id(
                raw.get("start_external_id"),
                f"segments[{line_number}].start_external_id",
            )
            goal_external = _external_id(
                raw.get("goal_external_id"),
                f"segments[{line_number}].goal_external_id",
            )
            if (
                start_external not in external_to_dense
                or goal_external not in external_to_dense
            ):
                raise PortableInputError(
                    f"segments[{line_number}] references an unknown external node"
                )
            start = external_to_dense[start_external]
            goal = external_to_dense[goal_external]
            leg = raw.get("leg")
            if leg not in {"direct", "storage_in", "storage_out"}:
                raise PortableInputError(
                    f"segments[{line_number}].leg is not a supported lifecycle leg"
                )

            if leg == "direct":
                role_ok = start in profile.start_nodes and goal in profile.goal_nodes
            elif selected_pair is None:
                raise PortableInputError(
                    "storage legs require an explicitly selected EBS pair"
                )
            elif leg == "storage_in":
                role_ok = (
                    start in profile.start_nodes
                    and goal == selected_pair.storage_in_goal
                )
            else:
                role_ok = (
                    start == selected_pair.storage_out_start
                    and goal in profile.goal_nodes
                )
            if not role_ok:
                raise PortableInputError(
                    f"segments[{line_number}] endpoints do not match explicit roles"
                )
            od = (start, goal)
            if od not in reachability:
                reachability[od] = _is_reachable(adjacency, start, goal)
            if not reachability[od]:
                raise PortableInputError(
                    f"segments[{line_number}] nominal OD is unreachable"
                )

            row: dict[str, Any] = {
                "segment_id": segment_id,
                "task_id": task_id,
                "pass_time": release,
                "std": deadline,
                "start": start,
                "goal": goal,
                "start_external_id": start_external,
                "goal_external_id": goal_external,
                "leg": leg,
            }
            source = raw.get("source")
            if source is not None:
                if not isinstance(source, str):
                    raise PortableInputError(
                        f"segments[{line_number}].source must be a string"
                    )
                row["source"] = source
            rows.append(row)

    if len(rows) != segment_count:
        raise PortableInputError(
            f"segment_count declares {segment_count}, loaded {len(rows)}"
        )
    return PortableWorkload(
        source_path=path,
        map_id=profile.map_id,
        storage_pair_id=storage_pair_id,
        rows=tuple(rows),
    )


def load_portable_fault_scenarios(
    protocol_path: str | Path,
    profile: map_adapter.RuntimeMapProfile,
) -> tuple[PortableFaultScenario, ...]:
    """Load pre-selected external-ID fault windows for the portable profile."""

    external_to_dense = _portable_profile(profile)
    _path, protocol = _read_object(protocol_path, "portable fault protocol")
    if protocol.get("schema") != PORTABLE_FAULT_SCHEMA:
        raise PortableInputError("unsupported portable fault schema")
    if protocol.get("map_id") != profile.map_id:
        raise PortableInputError("portable fault map_id does not match profile")
    raw_scenarios = protocol.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise PortableInputError("fault scenarios must be a non-empty list")

    graph_edges = {
        (int(start), int(end))
        for start, end, _length, _speed in profile.edge_records
    }
    scenario_ids: set[str] = set()
    scenarios: list[PortableFaultScenario] = []
    for scenario_index, raw_scenario in enumerate(raw_scenarios):
        if not isinstance(raw_scenario, Mapping):
            raise PortableInputError(
                f"scenarios[{scenario_index}] must be an object"
            )
        scenario_id = _external_id(
            raw_scenario.get("scenario_id"),
            f"scenarios[{scenario_index}].scenario_id",
        )
        if scenario_id in scenario_ids:
            raise PortableInputError(f"duplicate scenario_id: {scenario_id}")
        scenario_ids.add(scenario_id)
        raw_windows = raw_scenario.get("windows")
        if not isinstance(raw_windows, list) or not raw_windows:
            raise PortableInputError(
                f"scenarios[{scenario_index}].windows must be a non-empty list"
            )
        windows: list[tuple[int, int, float, float, float, bool]] = []
        for window_index, raw_window in enumerate(raw_windows):
            label = f"scenarios[{scenario_index}].windows[{window_index}]"
            if not isinstance(raw_window, Mapping):
                raise PortableInputError(f"{label} must be an object")
            start_external = _external_id(
                raw_window.get("start_external_id"), f"{label}.start_external_id"
            )
            end_external = _external_id(
                raw_window.get("end_external_id"), f"{label}.end_external_id"
            )
            if (
                start_external not in external_to_dense
                or end_external not in external_to_dense
            ):
                raise PortableInputError(f"{label} references an unknown node")
            start = external_to_dense[start_external]
            end = external_to_dense[end_external]
            if (start, end) not in graph_edges:
                raise PortableInputError(f"{label} is not a directed map edge")
            fault_time = _finite(raw_window.get("fault_time"), f"{label}.fault_time")
            repair_time = _finite(
                raw_window.get("repair_time"), f"{label}.repair_time"
            )
            message_delay = _finite(
                raw_window.get("message_delay", 0.0), f"{label}.message_delay"
            )
            drop_notification = raw_window.get("drop_notification", False)
            if fault_time < 0.0 or repair_time <= fault_time:
                raise PortableInputError(
                    f"{label} requires 0 <= fault_time < repair_time"
                )
            if message_delay < 0.0:
                raise PortableInputError(f"{label}.message_delay must be non-negative")
            if not isinstance(drop_notification, bool):
                raise PortableInputError(f"{label}.drop_notification must be boolean")
            windows.append(
                (
                    start,
                    end,
                    fault_time,
                    repair_time,
                    message_delay,
                    drop_notification,
                )
            )
        scenarios.append(
            PortableFaultScenario(
                scenario_id=scenario_id,
                fault_windows=tuple(windows),
            )
        )
    return tuple(scenarios)
