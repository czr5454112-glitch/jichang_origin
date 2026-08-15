#!/usr/bin/env python3
"""Probe safe parallelism around the frozen G24 A0+S4+J2+E2 runtime.

The probe deliberately separates two claims:

* ``same_stream`` is an observational feasibility audit over the native
  instrumented traces of two exact-release canaries: the canonical prefix and
  the deterministic densest release window.  It does not mutate the serial
  production runtime.  Trace coverage and optimistic bounds for untraced
  coordination events are reported explicitly.
* ``independent_runs`` measures aggregate throughput for two complete,
  independent runtime instances in a Python ``ThreadPoolExecutor``.  It is
  not a claim about one order stream's latency.

Production evidence uses the complete canonical input, the exact published
Java lifecycle releases, and one explicitly identified Release ``.pyd``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf19_bounded_capacity as g19
from scripts.eval import run_g4irsf20_event_hotpath as g20
from scripts.eval import run_g4irsf24_native_race as g24_race


SCHEMA = "czr005.g4irsf25.parallel_probe.v1"
DEFAULT_RELEASE_CSV = ROOT / "artifacts/datasets/g4irsf24_release_compact.csv"
DEFAULT_RELEASE_BINARY_DIR = ROOT / "build/g4irsf24_dlp_release/python"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf25_parallel_probe.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf25_parallel_probe.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf25_parallel_probe.md"
DEFAULT_TRACE_SEGMENTS = 512
DEFAULT_ROUNDS = 2
PARALLEL_THROUGHPUT_GATE = 1.70
PARALLEL_INDIVIDUAL_WALL_REGRESSION_MAX = 0.10
SAME_STREAM_MIN_EFFECTIVE_WIDTH = 1.70
SAME_STREAM_MIN_PARALLEL_FRACTION = 0.50
SAME_STREAM_MAX_TOP_OWNER_SHARE = 0.50
TIME_EPSILON = 1.0e-9

Executor = Callable[..., Mapping[str, Any]]
RequestFactory = Callable[[str, str, int], Mapping[str, Any]]


class ParallelProbeError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParallelProbeError(message)


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _find_release_binary(directory: Path = DEFAULT_RELEASE_BINARY_DIR) -> Path:
    candidates = sorted(directory.glob("czr005_cpp*.pyd"))
    if len(candidates) != 1:
        raise ParallelProbeError(
            f"expected exactly one Release czr005_cpp .pyd in {directory}; "
            f"found {len(candidates)}"
        )
    return candidates[0]


def _validate_release_binary(path: Path) -> dict[str, Any]:
    binary = path.resolve(strict=True)
    release_named = any("release" in part.lower() for part in binary.parts)
    valid_module = (
        binary.suffix.lower() == ".pyd"
        and binary.name.startswith("czr005_cpp")
        and binary.stat().st_size > 0
    )
    _require(
        valid_module and release_named,
        "binary is not an identified Release czr005_cpp .pyd",
    )
    return {
        "path": _portable_path(binary),
        "size_bytes": binary.stat().st_size,
        "release_build_path_pass": release_named,
    }


def load_exact_lifecycle(
    release_csv: Path,
) -> tuple[harness.InputPrefix, dict[str, Any]]:
    """Load all 43,603 canonical segments with the exact Java release epochs."""

    release_path = release_csv.resolve(strict=True)
    prefix = harness.load_input_prefix(harness.FULL_SIZE_SEGMENTS, root=ROOT)
    with release_path.open("r", encoding="utf-8", newline="") as handle:
        lifecycle = list(csv.DictReader(handle))
    required_fields = {"segment_id", "task_id", "start", "goal", "release_epoch"}
    fieldnames = set(lifecycle[0]) if lifecycle else set()
    ids = [str(row.get("segment_id", "")) for row in lifecycle]
    selected_ids = [str(row["segment_id"]) for row in prefix.rows]
    lifecycle_by_id = {
        str(row.get("segment_id", "")): row for row in lifecycle
    }
    metadata_matches = True
    releases_finite = True
    try:
        for source in prefix.rows:
            evidence = lifecycle_by_id[str(source["segment_id"])]
            metadata_matches = metadata_matches and (
                int(evidence["task_id"]) == int(source["task_id"])
                and int(evidence["start"]) == int(source["start"])
                and int(evidence["goal"]) == int(source["goal"])
            )
            releases_finite = releases_finite and math.isfinite(
                float(evidence["release_epoch"])
            )
    except (KeyError, TypeError, ValueError):
        metadata_matches = False
        releases_finite = False
    gates = {
        "complete_canonical_segment_count": (
            len(prefix.rows) == harness.FULL_SIZE_SEGMENTS
        ),
        "release_row_count_exact": len(lifecycle) == len(prefix.rows),
        "release_fields_present": required_fields.issubset(fieldnames),
        "release_segment_ids_nonempty": all(ids),
        "release_segment_ids_unique": len(ids) == len(set(ids)),
        "release_segment_id_set_exact": set(ids) == set(selected_ids),
        "release_task_start_goal_match_canonical": metadata_matches,
        "release_epochs_finite": releases_finite,
    }
    _require(all(gates.values()), "exact lifecycle release contract failed")
    adjusted, _alignment = g24_race.apply_exact_hca_releases(prefix, release_path)
    return adjusted, {
        "input": "data/processed/tasks/inputdata.jsonl",
        "release_csv": _portable_path(release_path),
        "release_row_count": len(lifecycle),
        "segment_count": len(adjusted.rows),
        "raw_bag_count": adjusted.raw_bag_count,
        "gates": gates,
        "pass": True,
    }


def load_exact_trace_canary(
    release_csv: Path,
    *,
    trace_segments: int,
) -> harness.InputPrefix:
    """Load an exact-release prefix whose runtime trace is retained in full."""

    _require(
        trace_segments in harness.SIZE_LADDER,
        f"trace segments must be one of {harness.SIZE_LADDER}",
    )
    _require(
        trace_segments < harness.FULL_SIZE_SEGMENTS,
        "trace canary must be smaller than the full throughput lifecycle",
    )
    canonical = harness.load_input_prefix(trace_segments, root=ROOT)
    adjusted, _alignment = g24_race.apply_exact_hca_releases(
        canonical, release_csv.resolve(strict=True)
    )
    return adjusted


def _trace_prefix_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> harness.InputPrefix:
    copied = tuple(dict(row) for row in rows)
    _require(bool(copied), "trace window must contain at least one row")
    segment_ids = [str(row["segment_id"]) for row in copied]
    _require(
        len(segment_ids) == len(set(segment_ids)),
        "trace window segment IDs must be unique",
    )
    return harness.InputPrefix(
        len(copied),
        copied,
        "not_recorded_for_g25_trace_window",
        len({int(row["task_id"]) for row in copied}),
        segment_ids[0],
        segment_ids[-1],
    )


def _release_window_metadata(
    rows: Sequence[Mapping[str, Any]],
    *,
    full_rows: Sequence[Mapping[str, Any]],
    window_kind: str,
    sorted_start_index: int | None,
) -> dict[str, Any]:
    releases = [float(row["pass_time"]) for row in rows]
    full_releases = [float(row["pass_time"]) for row in full_rows]
    release_span = max(releases) - min(releases)
    full_span = max(full_releases) - min(full_releases)
    ordinals = [
        int(row.get("input_row_index", fallback))
        for fallback, row in enumerate(rows)
    ]
    return {
        "window_kind": window_kind,
        "segment_count": len(rows),
        "raw_bag_count": len({int(row["task_id"]) for row in rows}),
        "release_epoch_min": min(releases),
        "release_epoch_max": max(releases),
        "release_span_seconds": release_span,
        "release_density_segments_per_second": (
            len(rows) / release_span if release_span > 0.0 else None
        ),
        "row_fraction_of_full_lifecycle": len(rows) / len(full_rows),
        "release_span_fraction_of_full_lifecycle": (
            release_span / full_span if full_span > 0.0 else 0.0
        ),
        "canonical_ordinal_min": min(ordinals),
        "canonical_ordinal_max": max(ordinals),
        "first_segment_id": str(rows[0]["segment_id"]),
        "last_segment_id": str(rows[-1]["segment_id"]),
        "release_sorted_start_index": sorted_start_index,
    }


def select_prefix_release_window(
    full_prefix: harness.InputPrefix,
    *,
    window_size: int = DEFAULT_TRACE_SEGMENTS,
) -> tuple[harness.InputPrefix, dict[str, Any]]:
    _require(0 < window_size <= len(full_prefix.rows), "invalid prefix window size")
    rows = full_prefix.rows[:window_size]
    return _trace_prefix_from_rows(rows), _release_window_metadata(
        rows,
        full_rows=full_prefix.rows,
        window_kind="canonical_prefix",
        sorted_start_index=None,
    )


def select_densest_release_window(
    full_prefix: harness.InputPrefix,
    *,
    window_size: int = DEFAULT_TRACE_SEGMENTS,
) -> tuple[harness.InputPrefix, dict[str, Any]]:
    """Select the deterministic minimum-span release-sorted sliding window."""

    _require(0 < window_size <= len(full_prefix.rows), "invalid dense window size")

    def ordinal(row: Mapping[str, Any], fallback: int) -> int:
        value = row.get("input_row_index")
        return int(value) if type(value) is int else fallback

    ordered = sorted(
        enumerate(full_prefix.rows),
        key=lambda pair: (
            float(pair[1]["pass_time"]),
            str(pair[1]["segment_id"]),
            ordinal(pair[1], pair[0]),
        ),
    )
    best_start = min(
        range(len(ordered) - window_size + 1),
        key=lambda start: (
            float(ordered[start + window_size - 1][1]["pass_time"])
            - float(ordered[start][1]["pass_time"]),
            str(ordered[start][1]["segment_id"]),
            ordinal(ordered[start][1], ordered[start][0]),
            str(ordered[start + window_size - 1][1]["segment_id"]),
            ordinal(
                ordered[start + window_size - 1][1],
                ordered[start + window_size - 1][0],
            ),
            start,
        ),
    )
    rows = tuple(
        dict(row) for _source_index, row in ordered[best_start : best_start + window_size]
    )
    metadata = _release_window_metadata(
        rows,
        full_rows=full_prefix.rows,
        window_kind="densest_release_sorted_contiguous",
        sorted_start_index=best_start,
    )
    metadata["selection_rule"] = (
        "minimum release span among release-sorted contiguous windows; "
        "ties by first/last segment_id, canonical ordinal, then sorted index"
    )
    return _trace_prefix_from_rows(rows), metadata


def build_s4_request(
    prefix: harness.InputPrefix,
    *,
    binary: Path,
    scenario: str,
    trace_limit: int,
    event_trace_limit: int,
) -> dict[str, Any]:
    request = g20.build_native_request(
        prefix.rows,
        scale=1,
        policy="E2",
        binary=binary,
        root=ROOT,
        bounded_wall_seconds=60.0,
        check_events=65_536,
    )
    request.update(
        scenario=scenario,
        summary_only=False,
        trace_limit=trace_limit,
        event_trace_limit=event_trace_limit,
    )
    return request


# Event priorities are the exact E4 production microphases used by S4/J2.
# E1/E2 here refer to the older event-semantics modes, not the G20 hotpath
# policy.  The production tuple is E4 + G20 E2.
E4_PHASES = {
    "FAULT": 0,
    "REPAIR": 0,
    "EDGE_EXIT": 1,
    "JUNCTION_SERVICE_COMPLETE": 1,
    "ARRIVE_JUNCTION": 2,
    "BAG_RELEASE": 2,
    "CONGESTION_BEACON_UPDATE": 3,
    "LOCAL_QUEUE_UPDATE": 3,
    "SOURCE_ARBITRATION": 4,
    "JUNCTION_ARBITRATION": 5,
    "DESTINATION_MERGE_ARBITRATION": 6,
    "EDGE_ENTER": 7,
}
LEGACY_PHASES = {
    "FAULT": 0,
    "REPAIR": 0,
    "EDGE_EXIT": 2,
    "JUNCTION_SERVICE_COMPLETE": 3,
    "ARRIVE_JUNCTION": 4,
    "CONGESTION_BEACON_UPDATE": 5,
    "BAG_RELEASE": 6,
    "SOURCE_ARBITRATION": 7,
    "JUNCTION_ARBITRATION": 8,
    "DESTINATION_MERGE_ARBITRATION": 9,
    "EDGE_ENTER": 10,
    "LOCAL_QUEUE_UPDATE": 11,
}


def _nominal_microphase(event_name: str, event_semantics: str) -> int:
    if event_semantics in {
        "E3_batch_source_and_junction_same_timestamp",
        "E4_batch_plus_destination_merge_request",
    }:
        return E4_PHASES.get(event_name, 8)
    return LEGACY_PHASES.get(event_name, 12)


def _decision_by_arrive_seq(
    decisions: Sequence[Mapping[str, Any]],
) -> dict[int, list[Mapping[str, Any]]]:
    by_seq: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for decision in decisions:
        metadata = decision.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        seq = metadata.get("arrive_event_seq")
        if type(seq) is int:
            by_seq[int(seq)].append(decision)
    return by_seq


def _node_values(values: Iterable[Any]) -> set[int]:
    return {
        int(value)
        for value in values
        if type(value) is int and int(value) >= 0
    }


def _decision_footprint(decision: Mapping[str, Any]) -> set[int]:
    candidates = decision.get("candidate_next_nodes")
    candidate_values = candidates if isinstance(candidates, list) else []
    return _node_values(
        [
            decision.get("current_node"),
            decision.get("selected_next"),
            decision.get("fallback_selected_next"),
            *candidate_values,
        ]
    )


def _event_footprint(
    event: Mapping[str, Any],
    linked_decisions: Sequence[Mapping[str, Any]],
) -> tuple[set[int], bool]:
    footprint = _node_values(
        [event.get("node"), event.get("from_node"), event.get("to_node")]
    )
    for decision in linked_decisions:
        footprint.update(_decision_footprint(decision))
    # Fault/repair rows do not expose notification-vs-physical generation;
    # treating them as a global barrier is conservative.  An empty footprint
    # is likewise never declared independent.
    global_barrier = str(event.get("event", "")) in {"FAULT", "REPAIR"} or not footprint
    return footprint, global_barrier


def _owner_node(item: Mapping[str, Any]) -> int | None:
    value = item.get("owner")
    return int(value) if type(value) is int and int(value) >= 0 else None


def _conflict_free_waves(items: Sequence[Mapping[str, Any]]) -> list[list[int]]:
    """First-fit deterministic waves; global barriers always occupy one wave."""

    waves: list[list[int]] = []
    wave_nodes: list[set[int]] = []
    wave_global: list[bool] = []
    for index, item in enumerate(items):
        footprint = set(item["footprint"])
        barrier = bool(item["global_barrier"])
        placed = False
        if not barrier:
            for wave_index, occupied in enumerate(wave_nodes):
                if not wave_global[wave_index] and footprint.isdisjoint(occupied):
                    waves[wave_index].append(index)
                    occupied.update(footprint)
                    placed = True
                    break
        if not placed:
            waves.append([index])
            wave_nodes.append(set(footprint))
            wave_global.append(barrier)
    return waves


def _analyze_items(
    items: Sequence[Mapping[str, Any]],
    *,
    trace_kind: str,
) -> dict[str, Any]:
    groups: dict[tuple[float, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        groups[(float(item["time"]), int(item["microphase"]))].append(item)

    group_rows: list[dict[str, Any]] = []
    all_wave_widths: list[int] = []
    conflict_free_parallel_items = 0
    total_waves = 0
    for (event_time, microphase), group in groups.items():
        waves = _conflict_free_waves(group)
        widths = [len(wave) for wave in waves]
        all_wave_widths.extend(widths)
        total_waves += len(waves)
        conflict_free_parallel_items += sum(width for width in widths if width >= 2)
        group_rows.append(
            {
                "trace_kind": trace_kind,
                "time": event_time,
                "microphase": microphase,
                "item_count": len(group),
                "wave_count": len(waves),
                "max_conflict_free_width": max(widths, default=0),
                "parallel_item_count": sum(width for width in widths if width >= 2),
                "global_barrier_count": sum(
                    1 for item in group if bool(item["global_barrier"])
                ),
            }
        )

    owners = Counter(
        owner for item in items if (owner := _owner_node(item)) is not None
    )
    owner_loads = list(owners.values())
    owner_mean = statistics.fmean(owner_loads) if owner_loads else 0.0
    owner_stddev = statistics.pstdev(owner_loads) if len(owner_loads) > 1 else 0.0
    total = len(items)
    raw_parallel_items = sum(
        len(group) for group in groups.values() if len(group) >= 2
    )
    global_count = sum(1 for item in items if bool(item["global_barrier"]))
    result = {
        "trace_kind": trace_kind,
        "item_count": total,
        "time_microphase_group_count": len(groups),
        "raw_parallel_item_count": raw_parallel_items,
        "raw_parallel_item_fraction": raw_parallel_items / total if total else 0.0,
        "conflict_free_parallel_item_count": conflict_free_parallel_items,
        "conflict_free_parallel_item_fraction": (
            conflict_free_parallel_items / total if total else 0.0
        ),
        "effective_width": total / total_waves if total_waves else 0.0,
        "max_conflict_free_width": max(all_wave_widths, default=0),
        "p50_conflict_free_width": _quantile(all_wave_widths, 0.50),
        "p95_conflict_free_width": _quantile(all_wave_widths, 0.95),
        "conflict_free_wave_width_histogram": [
            {
                "width": width,
                "wave_count": count,
                "wave_fraction": count / len(all_wave_widths),
            }
            for width, count in sorted(Counter(all_wave_widths).items())
        ],
        "global_barrier_count": global_count,
        "global_barrier_fraction": global_count / total if total else 0.0,
        "active_owner_node_count": len(owners),
        "top_owner_node": owners.most_common(1)[0][0] if owners else None,
        "top_owner_load": owners.most_common(1)[0][1] if owners else 0,
        "top_owner_share": (
            owners.most_common(1)[0][1] / sum(owner_loads) if owner_loads else 1.0
        ),
        "max_to_mean_owner_load": (
            max(owner_loads) / owner_mean if owner_mean > 0.0 else None
        ),
        "owner_load_coefficient_of_variation": (
            owner_stddev / owner_mean if owner_mean > 0.0 else None
        ),
        "owner_loads": [
            {"node": node, "item_count": count}
            for node, count in sorted(owners.items())
        ],
        "groups": sorted(
            group_rows,
            key=lambda row: (float(row["time"]), int(row["microphase"])),
        ),
    }
    return result


def _compact_trace_groups(
    analysis: Mapping[str, Any], *, max_anomalous_groups: int = 20
) -> None:
    """Replace full group rows with bounded aggregate evidence in-place."""

    _require(
        0 <= max_anomalous_groups <= 20,
        "max anomalous groups must be between zero and twenty",
    )
    for trace_kind in ("event", "decision"):
        section = analysis[trace_kind]
        _require(isinstance(section, dict), f"{trace_kind} analysis is not mutable")
        groups = section.pop("groups", [])
        microphases: dict[int, dict[str, Any]] = {}
        anomalies: list[dict[str, Any]] = []
        for group in groups:
            phase = int(group["microphase"])
            row = microphases.setdefault(
                phase,
                {
                    "microphase": phase,
                    "group_count": 0,
                    "item_count": 0,
                    "wave_count": 0,
                    "parallel_item_count": 0,
                    "global_barrier_count": 0,
                    "max_conflict_free_width": 0,
                },
            )
            row["group_count"] += 1
            for name in (
                "item_count",
                "wave_count",
                "parallel_item_count",
                "global_barrier_count",
            ):
                row[name] += int(group[name])
            row["max_conflict_free_width"] = max(
                int(row["max_conflict_free_width"]),
                int(group["max_conflict_free_width"]),
            )
            contention_excess = max(
                0,
                int(group["item_count"])
                - int(group["max_conflict_free_width"]),
            )
            if int(group["global_barrier_count"]) > 0 or contention_excess > 0:
                anomalies.append(
                    {**group, "contention_excess_item_count": contention_excess}
                )
        anomalies.sort(
            key=lambda row: (
                -int(row["global_barrier_count"]),
                -int(row["contention_excess_item_count"]),
                -int(row["item_count"]),
                float(row["time"]),
                int(row["microphase"]),
            )
        )
        section["microphase_summary"] = [
            microphases[phase] for phase in sorted(microphases)
        ]
        section["top_anomalous_groups"] = anomalies[:max_anomalous_groups]
        section["anomalous_group_count"] = len(anomalies)
        section["retained_anomalous_group_count"] = min(
            len(anomalies), max_anomalous_groups
        )


def analyze_trace_parallelism(
    events: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    *,
    event_semantics: str,
    event_trace_complete: bool = True,
    decision_trace_complete: bool = True,
) -> dict[str, Any]:
    """Reconstruct observed microphase floors and conservative node conflicts."""

    linked = _decision_by_arrive_seq(decisions)
    event_items: list[dict[str, Any]] = []
    phase_by_event_seq: dict[int, int] = {}
    previous_time: float | None = None
    floor = -1
    for ordinal, event in enumerate(events):
        event_time = float(event["time"])
        if previous_time is None or abs(event_time - previous_time) > TIME_EPSILON:
            floor = -1
        nominal = _nominal_microphase(str(event.get("event", "")), event_semantics)
        effective = max(floor, nominal)
        floor = effective
        previous_time = event_time
        seq = event.get("seq")
        if type(seq) is int:
            phase_by_event_seq[int(seq)] = effective
        event_decisions = linked.get(int(seq), []) if type(seq) is int else []
        footprint, barrier = _event_footprint(event, event_decisions)
        owner = next(
            (
                int(value)
                for value in (
                    event.get("node"),
                    event.get("from_node"),
                    event.get("to_node"),
                )
                if type(value) is int and int(value) >= 0
            ),
            None,
        )
        event_items.append(
            {
                "ordinal": ordinal,
                "time": event_time,
                "microphase": effective,
                "nominal_microphase": nominal,
                "footprint": sorted(footprint),
                "global_barrier": barrier,
                "owner": owner,
            }
        )

    decision_items: list[dict[str, Any]] = []
    for ordinal, decision in enumerate(decisions):
        footprint = _decision_footprint(decision)
        current = decision.get("current_node")
        metadata = decision.get("metadata")
        arrive_seq = (
            metadata.get("arrive_event_seq")
            if isinstance(metadata, Mapping)
            else None
        )
        origin_phase = (
            phase_by_event_seq.get(int(arrive_seq))
            if type(arrive_seq) is int
            else None
        )
        decision_items.append(
            {
                "ordinal": ordinal,
                "time": float(decision["event_time"]),
                # Complete event traces let every ordinary decision inherit
                # the reconstructed phase of its actual originating event.
                "microphase": origin_phase if origin_phase is not None else 8,
                "footprint": sorted(footprint),
                "global_barrier": not footprint or origin_phase is None,
                "owner": int(current) if type(current) is int and int(current) >= 0 else None,
            }
        )

    event_analysis = _analyze_items(event_items, trace_kind="event")
    decision_analysis = _analyze_items(decision_items, trace_kind="decision")
    exact_sample_gates = {
        "event_trace_nonempty": bool(events),
        "decision_trace_nonempty": bool(decisions),
        "event_trace_complete": event_trace_complete,
        "decision_trace_complete": decision_trace_complete,
        "production_event_semantics": (
            event_semantics == "E4_batch_plus_destination_merge_request"
        ),
    }
    opportunity_gates = {
        "event_effective_width_at_least_1_7": (
            event_analysis["effective_width"] >= SAME_STREAM_MIN_EFFECTIVE_WIDTH
        ),
        "decision_effective_width_at_least_1_7": (
            decision_analysis["effective_width"] >= SAME_STREAM_MIN_EFFECTIVE_WIDTH
        ),
        "event_parallel_fraction_at_least_0_5": (
            event_analysis["conflict_free_parallel_item_fraction"]
            >= SAME_STREAM_MIN_PARALLEL_FRACTION
        ),
        "decision_parallel_fraction_at_least_0_5": (
            decision_analysis["conflict_free_parallel_item_fraction"]
            >= SAME_STREAM_MIN_PARALLEL_FRACTION
        ),
        "event_top_owner_share_at_most_0_5": (
            event_analysis["top_owner_share"] <= SAME_STREAM_MAX_TOP_OWNER_SHARE
        ),
        "decision_top_owner_share_at_most_0_5": (
            decision_analysis["top_owner_share"] <= SAME_STREAM_MAX_TOP_OWNER_SHARE
        ),
        "no_unknown_global_barriers": (
            event_analysis["global_barrier_count"] == 0
            and decision_analysis["global_barrier_count"] == 0
        ),
    }
    go = all(exact_sample_gates.values()) and all(opportunity_gates.values())
    return {
        "method": {
            "group_key": "(event_time, reconstructed_effective_microphase)",
            "microphase_reconstruction": (
                "production nominal priority plus monotone observed same-time floor"
            ),
            "decision_microphase": (
                "reconstructed phase of metadata.arrive_event_seq; missing origin is a barrier"
            ),
            "footprint": (
                "current node + edge endpoints + linked decision candidate downstream nodes; "
                "fault/repair and empty footprints are global barriers"
            ),
            "scheduler_requirement": (
                "snapshot/stage per node footprint, then validate and commit in original "
                "(time,microphase,seq) order"
            ),
        },
        "event": event_analysis,
        "decision": decision_analysis,
        "sample_gates": exact_sample_gates,
        "opportunity_gates": opportunity_gates,
        "status": "GO" if go else "NO_GO",
        "go": go,
        "interpretation": (
            "feasibility recommendation only; the active runtime remains serial within one stream"
        ),
    }


def _runtime_tuple_gates(summary: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "scorer_is_s4": summary.get("scorer_mode") == g19.SCORER_MODES["S4"],
        "pibt_is_p2": summary.get("pibt_mode") == "P2",
        "merge_is_j2": (
            summary.get("merge_grant_timing_mode") == "jit_fair_aging_deadline"
        ),
        "event_semantics_is_e4": (
            summary.get("event_semantics")
            == "E4_batch_plus_destination_merge_request"
        ),
        "hotpath_is_e2": summary.get("g4irsf20_event_hotpath_policy") == "E2",
    }


BUSINESS_BAG_FIELDS = (
    "segment_id",
    "task_id",
    "runtime_bag_id",
    "start",
    "goal",
    "final_node",
    "arrival_time",
    "release_time",
    "deadline",
    "source",
    "admitted_time",
    "finish_time",
    "source_queue_delay",
    "total_local_wait",
    "junction_queue_wait_seconds",
    "merge_grant_wait_seconds",
    "edge_travel_time_seconds",
    "node_service_time_seconds",
    "loop_extra_time_seconds",
    "goal_completion_time_seconds",
    "decision_count",
    "retry_count",
    "loop_count",
    "completed",
    "starved",
    "failure_reason",
    "short_history",
)

def _business_projection(bags: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    projection = [
        {name: bag.get(name) for name in BUSINESS_BAG_FIELDS}
        for bag in bags
    ]
    return sorted(
        projection,
        key=lambda row: (
            int(row["runtime_bag_id"])
            if type(row.get("runtime_bag_id")) is int
            else -1,
            str(row.get("segment_id", "")),
        ),
    )


def _reduce_payload(
    payload: Mapping[str, Any],
    *,
    expected_segments: int,
) -> dict[str, Any]:
    summary = payload.get("summary")
    bags = payload.get("bags")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    _require(isinstance(bags, list), "native payload lacks bag rows")
    _require(
        all(isinstance(row, Mapping) for row in bags),
        "native payload contains a non-object bag row",
    )
    safety = g24_race._strict_s4_safety(summary, expected_segments)
    tuple_gates = _runtime_tuple_gates(summary)
    combined_safety = {
        "strict_s4_safety": safety,
        "runtime_tuple_gates": tuple_gates,
        "pass": bool(safety["pass"] and all(tuple_gates.values())),
    }
    business = _business_projection(bags)
    safety_projection = {
        "gates": safety["gates"],
        "runtime_tuple_gates": tuple_gates,
    }
    return {
        # Private in-memory structures are removed immediately after direct
        # equality comparison and are never written to JSON/CSV/Markdown.
        "_business_projection": business,
        "_safety_projection": safety_projection,
        "business_row_count": len(business),
        "completed_count": int(summary.get("completed_count", -1)),
        "event_count": int(summary.get("event_count", 0)),
        "decision_count": int(summary.get("decision_count", 0)),
        "safety_pass": combined_safety["pass"],
        "runtime_tuple": {
            "scorer": summary.get("scorer_mode"),
            "pibt": summary.get("pibt_mode"),
            "event_semantics": summary.get("event_semantics"),
            "merge_timing": summary.get("merge_grant_timing_mode"),
            "hotpath": summary.get("g4irsf20_event_hotpath_policy"),
        },
    }


def _invoke_once(
    executor: Executor, request: Mapping[str, Any]
) -> tuple[Mapping[str, Any], float]:
    """Measure exactly one end-to-end backend call, before projection checks."""

    started = time.perf_counter()
    payload = executor(**dict(request))
    wall_seconds = time.perf_counter() - started
    _require(isinstance(payload, Mapping), "executor returned a non-object payload")
    return payload, wall_seconds


def _finish_once(
    payload: Mapping[str, Any],
    wall_seconds: float,
    *,
    lane: str,
    mode: str,
    round_index: int,
    expected_segments: int,
) -> dict[str, Any]:
    reduced = _reduce_payload(payload, expected_segments=expected_segments)
    return {
        "lane": lane,
        "mode": mode,
        "round": round_index,
        "wall_seconds": wall_seconds,
        **reduced,
    }


def _sequential_order(round_index: int, policy: str) -> tuple[str, str]:
    if policy == "AB":
        return ("A", "B")
    if policy == "BA":
        return ("B", "A")
    if policy == "alternating":
        return ("A", "B") if round_index % 2 == 0 else ("B", "A")
    raise ParallelProbeError(f"unknown sequential lane order: {policy}")


def _mode_order(round_index: int, policy: str) -> tuple[str, str]:
    if policy == "sequential-first":
        return ("sequential", "parallel")
    if policy == "parallel-first":
        return ("parallel", "sequential")
    if policy == "alternating":
        return (
            ("sequential", "parallel")
            if round_index % 2 == 0
            else ("parallel", "sequential")
        )
    raise ParallelProbeError(f"unknown mode order: {policy}")


def run_throughput_probe(
    *,
    executor: Executor,
    request_factory: RequestFactory,
    expected_segments: int,
    rounds: int = DEFAULT_ROUNDS,
    sequential_lane_order: str = "alternating",
    mode_order: str = "alternating",
    throughput_gate: float = PARALLEL_THROUGHPUT_GATE,
) -> dict[str, Any]:
    """Compare two serial instances with the same two instances in threads."""

    _require(rounds >= 1, "rounds must be positive")
    _require(throughput_gate > 0.0, "throughput gate must be positive")
    pairs: list[dict[str, Any]] = []
    all_runs: list[dict[str, Any]] = []
    reference_business: list[dict[str, Any]] | None = None
    reference_safety: dict[str, Any] | None = None
    reference_counts: tuple[int, int, int, int] | None = None

    def compare_and_discard(run: dict[str, Any]) -> None:
        nonlocal reference_business, reference_safety, reference_counts
        business = run.pop("_business_projection")
        safety = run.pop("_safety_projection")
        counts = (
            int(run["business_row_count"]),
            int(run["completed_count"]),
            int(run["event_count"]),
            int(run["decision_count"]),
        )
        if reference_business is None:
            reference_business = business
            reference_safety = safety
            reference_counts = counts
        run["business_equivalent_to_reference"] = bool(
            business == reference_business and counts == reference_counts
        )
        run["safety_equivalent_to_reference"] = bool(
            safety == reference_safety and bool(run["safety_pass"])
        )
        run["equivalence_pass"] = bool(
            run["business_equivalent_to_reference"]
            and run["safety_equivalent_to_reference"]
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="g4irsf25") as pool:
        for round_index in range(rounds):
            for mode in _mode_order(round_index, mode_order):
                if mode == "sequential":
                    lane_order = _sequential_order(round_index, sequential_lane_order)
                    requests = {
                        lane: request_factory(lane, mode, round_index)
                        for lane in lane_order
                    }
                    invoked = {
                        lane: _invoke_once(executor, requests[lane])
                        for lane in lane_order
                    }
                    pair_wall = sum(wall for _payload, wall in invoked.values())
                    runs = [
                        _finish_once(
                            invoked[lane][0],
                            invoked[lane][1],
                            lane=lane,
                            mode=mode,
                            round_index=round_index,
                            expected_segments=expected_segments,
                        )
                        for lane in lane_order
                    ]
                else:
                    lane_order = ("A", "B")
                    requests = {
                        lane: request_factory(lane, mode, round_index)
                        for lane in lane_order
                    }
                    pair_started = time.perf_counter()
                    futures = {
                        lane: pool.submit(
                            _invoke_once,
                            executor,
                            requests[lane],
                        )
                        for lane in lane_order
                    }
                    invoked = {lane: futures[lane].result() for lane in lane_order}
                    pair_wall = time.perf_counter() - pair_started
                    runs = [
                        _finish_once(
                            invoked[lane][0],
                            invoked[lane][1],
                            lane=lane,
                            mode=mode,
                            round_index=round_index,
                            expected_segments=expected_segments,
                        )
                        for lane in lane_order
                    ]
                for run in runs:
                    compare_and_discard(run)
                event_count = sum(int(run["event_count"]) for run in runs)
                pairs.append(
                    {
                        "round": round_index,
                        "mode": mode,
                        "lane_order": list(lane_order),
                        "pair_wall_seconds": pair_wall,
                        "sum_individual_wall_seconds": sum(
                            float(run["wall_seconds"]) for run in runs
                        ),
                        "overlap_factor": (
                            sum(float(run["wall_seconds"]) for run in runs) / pair_wall
                            if pair_wall > 0.0
                            else None
                        ),
                        "aggregate_event_count": event_count,
                        "aggregate_events_per_wall_second": (
                            event_count / pair_wall if pair_wall > 0.0 else None
                        ),
                    }
                )
                all_runs.extend(runs)

    by_mode = {
        mode: [pair for pair in pairs if pair["mode"] == mode]
        for mode in ("sequential", "parallel")
    }
    mode_summary: dict[str, dict[str, Any]] = {}
    for mode, mode_pairs in by_mode.items():
        mode_runs = [run for run in all_runs if run["mode"] == mode]
        total_events = sum(int(pair["aggregate_event_count"]) for pair in mode_pairs)
        total_wall = sum(float(pair["pair_wall_seconds"]) for pair in mode_pairs)
        mode_summary[mode] = {
            "pair_count": len(mode_pairs),
            "aggregate_event_count": total_events,
            "aggregate_wall_seconds": total_wall,
            "aggregate_events_per_wall_second": (
                total_events / total_wall if total_wall > 0.0 else None
            ),
            "median_pair_wall_seconds": statistics.median(
                float(pair["pair_wall_seconds"]) for pair in mode_pairs
            ),
            "median_overlap_factor": statistics.median(
                float(pair["overlap_factor"]) for pair in mode_pairs
            ),
            "median_individual_wall_seconds": statistics.median(
                float(run["wall_seconds"]) for run in mode_runs
            ),
        }
    sequential_eps = float(mode_summary["sequential"]["aggregate_events_per_wall_second"])
    parallel_eps = float(mode_summary["parallel"]["aggregate_events_per_wall_second"])
    speedup = parallel_eps / sequential_eps if sequential_eps > 0.0 else 0.0
    sequential_individual_wall = float(
        mode_summary["sequential"]["median_individual_wall_seconds"]
    )
    parallel_individual_wall = float(
        mode_summary["parallel"]["median_individual_wall_seconds"]
    )
    individual_wall_regression = (
        parallel_individual_wall / sequential_individual_wall - 1.0
        if sequential_individual_wall > 0.0
        else math.inf
    )
    equivalence_pass = all(bool(run["equivalence_pass"]) for run in all_runs)
    batch_gates = {
        "parallel_aggregate_throughput_at_least_1_7x": speedup >= throughput_gate,
        "every_run_business_equivalent": all(
            bool(run["business_equivalent_to_reference"]) for run in all_runs
        ),
        "every_run_safety_equivalent_and_pass": all(
            bool(run["safety_equivalent_to_reference"]) for run in all_runs
        ),
        "same_work_count_in_both_modes": (
            mode_summary["sequential"]["aggregate_event_count"]
            == mode_summary["parallel"]["aggregate_event_count"]
        ),
    }
    batch_throughput_go = all(batch_gates.values()) and equivalence_pass
    latency_guard_pass = (
        math.isfinite(individual_wall_regression)
        and individual_wall_regression
        <= PARALLEL_INDIVIDUAL_WALL_REGRESSION_MAX + 1.0e-12
    )
    gates = {
        **batch_gates,
        "parallel_individual_wall_regression_at_most_0_10": latency_guard_pass,
    }
    go = batch_throughput_go and latency_guard_pass
    status = (
        "GO"
        if go
        else "GO_BATCH_THROUGHPUT_ONLY"
        if batch_throughput_go
        else "NO_GO"
    )
    deployment_scope = (
        "offline_or_independent_runtime_batch_only"
        if status in {"GO", "GO_BATCH_THROUGHPUT_ONLY"}
        else "not_promoted"
    )
    return {
        "claim_scope": (
            "offline/batch aggregate throughput of two independent complete S4 runs; "
            "not the default for one latency-sensitive live order stream"
        ),
        "executor": "concurrent.futures.ThreadPoolExecutor(max_workers=2)",
        "rounds": rounds,
        "sequential_lane_order": sequential_lane_order,
        "mode_order": mode_order,
        "threshold": {
            "parallel_aggregate_speedup_min": throughput_gate,
            "parallel_individual_wall_regression_max": (
                PARALLEL_INDIVIDUAL_WALL_REGRESSION_MAX
            ),
        },
        "pairs": pairs,
        "runs": all_runs,
        "summary": mode_summary,
        "aggregate_speedup": speedup,
        "parallel_individual_wall_regression_fraction": individual_wall_regression,
        "latency_guard_pass": latency_guard_pass,
        "batch_throughput_go": batch_throughput_go,
        "deployment_scope": deployment_scope,
        "equivalence_pass": equivalence_pass,
        "gates": gates,
        "status": status,
        "go": go,
    }


def _trace_probe(
    *,
    executor: Executor,
    prefix: harness.InputPrefix,
    binary: Path,
    scenario: str = "g4irsf25_same_stream_trace",
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = build_s4_request(
        prefix,
        binary=binary,
        scenario=scenario,
        trace_limit=-1,
        event_trace_limit=-1,
    )
    started = time.perf_counter()
    payload = executor(**request)
    wall_seconds = time.perf_counter() - started
    _require(isinstance(payload, Mapping), "trace executor returned a non-object")
    summary = payload.get("summary")
    events = payload.get("events")
    decisions = payload.get("decisions")
    holds = payload.get("hold_attempts")
    _require(isinstance(summary, Mapping), "trace payload lacks summary")
    _require(isinstance(events, list), "trace payload lacks event rows")
    _require(isinstance(decisions, list), "trace payload lacks decision rows")
    _require(isinstance(holds, list), "trace payload lacks hold rows")
    decision_trace = [*decisions, *holds]
    decision_trace.sort(
        key=lambda row: (
            float(row.get("event_time", 0.0)),
            int(row.get("metadata", {}).get("arrive_event_seq", -1))
            if isinstance(row.get("metadata"), Mapping)
            else -1,
            str(row.get("decision_id", "")),
        )
    )
    safety = _reduce_payload(payload, expected_segments=len(prefix.rows))
    processed_event_count = int(safety["event_count"])
    stored_event_count = len(events)
    untraced_event_count = max(0, processed_event_count - stored_event_count)
    event_trace_untruncated = summary.get("event_trace_truncated") is False
    event_trace_complete = (
        event_trace_untruncated and stored_event_count == processed_event_count
    )
    analysis = analyze_trace_parallelism(
        events,
        decision_trace,
        event_semantics=str(summary.get("event_semantics", "")),
        event_trace_complete=event_trace_complete,
        decision_trace_complete=summary.get("decision_trace_truncated") is False,
    )
    event_analysis = analysis["event"]
    observed_wave_count = sum(
        int(row["wave_count"])
        for row in event_analysis["conflict_free_wave_width_histogram"]
    )
    optimistic_effective_width = (
        processed_event_count / observed_wave_count
        if observed_wave_count > 0
        else 0.0
    )
    optimistic_parallel_fraction = (
        (
            int(event_analysis["conflict_free_parallel_item_count"])
            + untraced_event_count
        )
        / processed_event_count
        if processed_event_count > 0
        else 0.0
    )
    untraced_destination_merge_count = int(
        summary.get("destination_merge_arbitration_event_count", 0)
    )
    untraced_stale_count = int(summary.get("stale_arbitration_event_count", 0))
    untraced_other_count = max(
        0,
        untraced_event_count
        - untraced_destination_merge_count
        - untraced_stale_count,
    )
    analysis["event_trace_observation"] = {
        "processed_event_count": processed_event_count,
        "stored_event_count": stored_event_count,
        "coverage_fraction": (
            stored_event_count / processed_event_count
            if processed_event_count > 0
            else 0.0
        ),
        "untraced_event_count": untraced_event_count,
        "event_trace_untruncated": event_trace_untruncated,
        "event_trace_complete": event_trace_complete,
        "untraced_destination_merge_arbitration_count": (
            untraced_destination_merge_count
        ),
        "untraced_stale_arbitration_count": untraced_stale_count,
        "untraced_other_event_count": untraced_other_count,
        "optimistic_effective_width_if_all_untraced_pack_existing_waves": (
            optimistic_effective_width
        ),
        "optimistic_parallel_item_fraction_if_all_untraced_are_parallel": (
            optimistic_parallel_fraction
        ),
        "optimistic_bounds_still_fail_opportunity_gates": (
            optimistic_effective_width < SAME_STREAM_MIN_EFFECTIVE_WIDTH
            and optimistic_parallel_fraction < SAME_STREAM_MIN_PARALLEL_FRACTION
        ),
    }
    _require(bool(safety["safety_pass"]), "trace run failed S4 safety/runtime tuple")
    metadata = {
        "wall_seconds": wall_seconds,
        "trace_segment_count": len(prefix.rows),
        "trace_raw_bag_count": prefix.raw_bag_count,
        "trace_limits": {"event": -1, "decision_or_hold": -1},
        "stored_event_trace_rows": len(events),
        "stored_decision_rows": len(decisions),
        "stored_hold_rows": len(holds),
        "stored_decision_or_hold_trace_rows": len(decision_trace),
        "event_trace_truncated": summary.get("event_trace_truncated"),
        "event_trace_complete": event_trace_complete,
        "event_trace_coverage_fraction": (
            stored_event_count / processed_event_count
            if processed_event_count > 0
            else 0.0
        ),
        "untraced_event_count": untraced_event_count,
        "decision_trace_truncated": summary.get("decision_trace_truncated"),
        "full_run_event_count": safety["event_count"],
        "full_run_decision_count": safety["decision_count"],
        "safety_pass": safety["safety_pass"],
        "runtime_tuple": safety["runtime_tuple"],
    }
    return analysis, metadata


def _assess_same_stream_window(
    analysis: Mapping[str, Any],
    trace_run: Mapping[str, Any],
    *,
    window_label: str,
    window_size: int,
) -> dict[str, Any]:
    """Apply the registered width/fraction gates without overstating coverage."""

    event = analysis["event"]
    decision = analysis["decision"]
    observation = analysis["event_trace_observation"]
    event_width_upper = float(
        observation[
            "optimistic_effective_width_if_all_untraced_pack_existing_waves"
        ]
    )
    event_fraction_upper = float(
        observation[
            "optimistic_parallel_item_fraction_if_all_untraced_are_parallel"
        ]
    )
    decision_width = float(decision["effective_width"])
    decision_fraction = float(decision["conflict_free_parallel_item_fraction"])
    evidence_gates = {
        "runtime_safety_pass": bool(trace_run["safety_pass"]),
        "event_trace_request_untruncated": bool(
            observation["event_trace_untruncated"]
        ),
        "decision_trace_complete": bool(
            analysis["sample_gates"]["decision_trace_complete"]
        ),
        "event_trace_nonempty": bool(
            analysis["sample_gates"]["event_trace_nonempty"]
        ),
        "decision_trace_nonempty": bool(
            analysis["sample_gates"]["decision_trace_nonempty"]
        ),
        "production_event_semantics": bool(
            analysis["sample_gates"]["production_event_semantics"]
        ),
    }
    width_gates = {
        "event_optimistic_effective_width_at_least_1_7": (
            event_width_upper >= SAME_STREAM_MIN_EFFECTIVE_WIDTH
        ),
        "decision_observed_effective_width_at_least_1_7": (
            decision_width >= SAME_STREAM_MIN_EFFECTIVE_WIDTH
        ),
    }
    fraction_gates = {
        "event_optimistic_parallel_fraction_at_least_0_5": (
            event_fraction_upper >= SAME_STREAM_MIN_PARALLEL_FRACTION
        ),
        "decision_observed_parallel_fraction_at_least_0_5": (
            decision_fraction >= SAME_STREAM_MIN_PARALLEL_FRACTION
        ),
    }
    evidence_valid = all(evidence_gates.values())
    width_gate_pass = all(width_gates.values())
    fraction_gate_pass = all(fraction_gates.values())
    passes_required_gates = width_gate_pass and fraction_gate_pass
    definitively_fails_required_gates = evidence_valid and not passes_required_gates
    if definitively_fails_required_gates:
        status = f"NO_GO_ON_{window_label.upper()}_{window_size}_CANARY"
    elif evidence_valid:
        status = (
            f"OPPORTUNITY_NOT_EXCLUDED_ON_{window_label.upper()}_"
            f"{window_size}_CANARY"
        )
    else:
        status = f"INCONCLUSIVE_ON_{window_label.upper()}_{window_size}_CANARY"
    return {
        "status": status,
        "evidence_valid": evidence_valid,
        "evidence_gates": evidence_gates,
        "width_gates": width_gates,
        "fraction_gates": fraction_gates,
        "width_gate_pass": width_gate_pass,
        "fraction_gate_pass": fraction_gate_pass,
        "passes_required_width_and_fraction_gates": passes_required_gates,
        "definitively_fails_any_required_width_or_fraction_gate": (
            definitively_fails_required_gates
        ),
        "event_observed_effective_width": float(event["effective_width"]),
        "event_observed_parallel_item_fraction": float(
            event["conflict_free_parallel_item_fraction"]
        ),
        "event_optimistic_effective_width_upper_bound": event_width_upper,
        "event_optimistic_parallel_item_fraction_upper_bound": (
            event_fraction_upper
        ),
        "decision_observed_effective_width": decision_width,
        "decision_observed_parallel_item_fraction": decision_fraction,
        "interpretation": (
            "bounded feasibility evidence only; a passing optimistic gate does not "
            "authorize implementation"
        ),
    }


def probe_same_stream_windows(
    *,
    executor: Executor,
    full_prefix: harness.InputPrefix,
    binary: Path,
    window_size: int = DEFAULT_TRACE_SEGMENTS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run prefix and peak-density exact-release canaries."""

    _require(
        window_size < len(full_prefix.rows),
        "same-stream canary must be smaller than the full lifecycle",
    )
    prefix, prefix_selection = select_prefix_release_window(
        full_prefix, window_size=window_size
    )
    peak, peak_selection = select_densest_release_window(
        full_prefix, window_size=window_size
    )
    specifications = (
        (
            "prefix",
            "PREFIX",
            prefix,
            prefix_selection,
            "g4irsf25_same_stream_prefix_trace",
        ),
        (
            "peak_release_density",
            "PEAK_RELEASE",
            peak,
            peak_selection,
            "g4irsf25_same_stream_peak_release_trace",
        ),
    )
    windows: dict[str, Any] = {}
    for key, status_label, selected, selection, scenario in specifications:
        analysis, trace_run = _trace_probe(
            executor=executor,
            prefix=selected,
            binary=binary,
            scenario=scenario,
        )
        assessment = _assess_same_stream_window(
            analysis,
            trace_run,
            window_label=status_label,
            window_size=window_size,
        )
        # The generic trace analyzer has an intentionally strict GO/NO_GO
        # result. Scope that result to this selected canary before persisting
        # it so a prefix-only NO_GO cannot be mistaken for a universal claim.
        analysis["status"] = assessment["status"]
        analysis["go"] = False
        analysis["implementation_authorized"] = False
        windows[key] = {
            "selection": selection,
            "trace_run": trace_run,
            "analysis": analysis,
            "opportunity_assessment": assessment,
        }

    failed = [
        bool(
            window["opportunity_assessment"][
                "definitively_fails_any_required_width_or_fraction_gate"
            ]
        )
        for window in windows.values()
    ]
    both_fail = len(failed) == 2 and all(failed)
    combined_status = (
        f"NO_GO_ON_TESTED_{window_size}_WINDOWS"
        if both_fail
        else f"OPPORTUNITY_NOT_EXCLUDED_ON_TESTED_{window_size}_WINDOWS"
    )
    combined = {
        "status": combined_status,
        "tested_window_count": len(windows),
        "window_size_segments": window_size,
        "both_tested_windows_definitively_fail_any_required_width_or_fraction_gate": (
            both_fail
        ),
        "implementation_authorized": False,
        "implementation_recommendation": "DEFER_SAME_STREAM_PARALLEL_IMPLEMENTATION",
        "extrapolation_to_larger_maps_or_new_workloads_allowed": False,
        "scope_limit": (
            f"two deterministic {window_size}-segment canaries only; results cannot be "
            "extrapolated to a larger map or a new workload"
        ),
    }
    protocol_windows = {
        key: {
            **dict(window["selection"]),
            "scope": (
                "complete exact-release canonical prefix"
                if key == "prefix"
                else "complete exact-release densest release-sorted window"
            ),
            "trace_limit": -1,
            "event_trace_limit": -1,
        }
        for key, window in windows.items()
    }
    same_stream = {
        # Retain the original prefix fields as compatibility aliases while the
        # two-window evidence is added append-only.
        "trace_run": windows["prefix"]["trace_run"],
        "analysis": windows["prefix"]["analysis"],
        "windows": windows,
        "combined_assessment": combined,
        "current_runtime_implementation": (
            "serial event loop; no same-stream worker mutation was added"
        ),
    }
    return same_stream, protocol_windows


def run_probe(
    *,
    binary: Path,
    release_csv: Path,
    rounds: int = DEFAULT_ROUNDS,
    trace_segments: int = DEFAULT_TRACE_SEGMENTS,
    sequential_lane_order: str = "alternating",
    mode_order: str = "alternating",
    executor: Executor = cpp_backend.g4irsf11_event_runtime_from_records,
) -> dict[str, Any]:
    binary_contract = _validate_release_binary(binary)
    prefix, lifecycle = load_exact_lifecycle(release_csv)
    _require(
        trace_segments in harness.SIZE_LADDER,
        f"trace segments must be one of {harness.SIZE_LADDER}",
    )
    same_stream, protocol_trace_windows = probe_same_stream_windows(
        executor=executor,
        full_prefix=prefix,
        binary=binary.resolve(strict=True),
        window_size=trace_segments,
    )
    base_request = build_s4_request(
        prefix,
        binary=binary.resolve(strict=True),
        scenario="g4irsf25_throughput_base",
        trace_limit=0,
        event_trace_limit=0,
    )

    def request_factory(lane: str, mode: str, round_index: int) -> Mapping[str, Any]:
        request = dict(base_request)
        request["scenario"] = f"g4irsf25_{mode}_r{round_index}_{lane.lower()}"
        return request

    throughput = run_throughput_probe(
        executor=executor,
        request_factory=request_factory,
        expected_segments=len(prefix.rows),
        rounds=rounds,
        sequential_lane_order=sequential_lane_order,
        mode_order=mode_order,
    )
    payload = {
        "schema": SCHEMA,
        "generated_at_epoch_seconds": time.time(),
        "protocol": {
            "binary": binary_contract,
            "lifecycle": lifecycle,
            "controller": "A0+S4+J2+E2",
            "trace_canary": {
                # Legacy alias for the canonical-prefix window.
                "scope": "complete exact-release canonical prefix",
                "segment_count": protocol_trace_windows["prefix"][
                    "segment_count"
                ],
                "raw_bag_count": protocol_trace_windows["prefix"][
                    "raw_bag_count"
                ],
                "trace_limit": -1,
                "event_trace_limit": -1,
            },
            "trace_windows": protocol_trace_windows,
            "same_stream_thresholds": {
                "effective_width_min": SAME_STREAM_MIN_EFFECTIVE_WIDTH,
                "parallel_item_fraction_min": SAME_STREAM_MIN_PARALLEL_FRACTION,
                "top_owner_share_max": SAME_STREAM_MAX_TOP_OWNER_SHARE,
            },
        },
        "same_stream": same_stream,
        "independent_runs": throughput,
        "decision": {
            "same_stream_node_parallel": same_stream["combined_assessment"][
                "status"
            ],
            "same_stream_implementation_recommendation": same_stream[
                "combined_assessment"
            ]["implementation_recommendation"],
            "same_stream_implementation_authorized": False,
            "same_stream_extrapolation_allowed": False,
            "independent_run_parallel_throughput": throughput["status"],
            "independent_run_deployment_scope": throughput["deployment_scope"],
            "single_stream_latency_claimed": False,
            "single_live_stream_parallel_default": False,
        },
    }
    for window in payload["same_stream"]["windows"].values():
        _compact_trace_groups(window["analysis"])
    return payload


CSV_FIELDS = (
    "record_type",
    "window",
    "trace_kind",
    "round",
    "mode",
    "lane",
    "time",
    "microphase",
    "item_count",
    "wave_count",
    "max_conflict_free_width",
    "parallel_item_count",
    "global_barrier_count",
    "pair_wall_seconds",
    "sum_individual_wall_seconds",
    "overlap_factor",
    "aggregate_event_count",
    "aggregate_events_per_wall_second",
    "run_wall_seconds",
    "business_equivalent",
    "safety_equivalent",
    "status",
    "median_individual_wall_seconds",
    "individual_wall_regression_fraction",
    "latency_guard_pass",
    "effective_width",
    "conflict_free_parallel_item_fraction",
    "top_owner_share",
    "width",
    "group_count",
    "wave_fraction",
    "release_epoch_min",
    "release_epoch_max",
    "release_span_seconds",
    "release_density_segments_per_second",
    "event_trace_coverage_fraction",
    "event_optimistic_effective_width_upper_bound",
    "event_optimistic_parallel_item_fraction_upper_bound",
    "decision_observed_effective_width",
    "decision_observed_parallel_item_fraction",
    "width_gate_pass",
    "fraction_gate_pass",
)


def _csv_bytes(payload: Mapping[str, Any]) -> bytes:
    rows: list[dict[str, Any]] = []
    for window_name, window in payload["same_stream"]["windows"].items():
        analysis = window["analysis"]
        assessment = window["opportunity_assessment"]
        selection = window["selection"]
        observation = analysis["event_trace_observation"]
        rows.append(
            {
                "record_type": "trace_window",
                "window": window_name,
                "item_count": selection["segment_count"],
                "release_epoch_min": selection["release_epoch_min"],
                "release_epoch_max": selection["release_epoch_max"],
                "release_span_seconds": selection["release_span_seconds"],
                "release_density_segments_per_second": selection[
                    "release_density_segments_per_second"
                ],
                "event_trace_coverage_fraction": observation[
                    "coverage_fraction"
                ],
                "event_optimistic_effective_width_upper_bound": assessment[
                    "event_optimistic_effective_width_upper_bound"
                ],
                "event_optimistic_parallel_item_fraction_upper_bound": assessment[
                    "event_optimistic_parallel_item_fraction_upper_bound"
                ],
                "decision_observed_effective_width": assessment[
                    "decision_observed_effective_width"
                ],
                "decision_observed_parallel_item_fraction": assessment[
                    "decision_observed_parallel_item_fraction"
                ],
                "width_gate_pass": assessment["width_gate_pass"],
                "fraction_gate_pass": assessment["fraction_gate_pass"],
                "status": assessment["status"],
            }
        )
        for trace_kind in ("event", "decision"):
            section = analysis[trace_kind]
            rows.append(
                {
                    "record_type": "trace_summary",
                    "window": window_name,
                    "trace_kind": trace_kind,
                    "item_count": section["item_count"],
                    "group_count": section["time_microphase_group_count"],
                    "max_conflict_free_width": section[
                        "max_conflict_free_width"
                    ],
                    "global_barrier_count": section["global_barrier_count"],
                    "effective_width": section["effective_width"],
                    "conflict_free_parallel_item_fraction": section[
                        "conflict_free_parallel_item_fraction"
                    ],
                    "top_owner_share": section["top_owner_share"],
                    "status": assessment["status"],
                }
            )
            for width in section["conflict_free_wave_width_histogram"]:
                rows.append(
                    {
                        "record_type": "trace_width_histogram",
                        "window": window_name,
                        "trace_kind": trace_kind,
                        **width,
                    }
                )
            for phase in section["microphase_summary"]:
                rows.append(
                    {
                        "record_type": "trace_microphase_summary",
                        "window": window_name,
                        "trace_kind": trace_kind,
                        **phase,
                    }
                )
    throughput = payload["independent_runs"]
    for pair in throughput["pairs"]:
        rows.append({"record_type": "throughput_pair", **pair})
    for run in throughput["runs"]:
        rows.append(
            {
                "record_type": "throughput_run",
                "round": run["round"],
                "mode": run["mode"],
                "lane": run["lane"],
                "run_wall_seconds": run["wall_seconds"],
                "aggregate_event_count": run["event_count"],
                "business_equivalent": run["business_equivalent_to_reference"],
                "safety_equivalent": run["safety_equivalent_to_reference"],
                "status": "PASS" if run["equivalence_pass"] else "FAIL",
            }
        )
    for mode, summary in throughput["summary"].items():
        rows.append(
            {
                "record_type": "throughput_mode_summary",
                "mode": mode,
                "aggregate_event_count": summary["aggregate_event_count"],
                "aggregate_events_per_wall_second": summary[
                    "aggregate_events_per_wall_second"
                ],
                "median_individual_wall_seconds": summary[
                    "median_individual_wall_seconds"
                ],
                "individual_wall_regression_fraction": (
                    throughput["parallel_individual_wall_regression_fraction"]
                    if mode == "parallel"
                    else 0.0
                ),
                "latency_guard_pass": throughput["latency_guard_pass"],
                "status": throughput["status"],
            }
        )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _report(payload: Mapping[str, Any]) -> str:
    same_stream = payload["same_stream"]
    windows = same_stream["windows"]
    combined = same_stream["combined_assessment"]
    window_size = int(combined["window_size_segments"])
    throughput = payload["independent_runs"]
    sequential = throughput["summary"]["sequential"]
    parallel = throughput["summary"]["parallel"]
    decision_row = payload["decision"]
    window_names = {
        "prefix": "Canonical prefix",
        "peak_release_density": "Densest release window",
    }
    window_contract_lines: list[str] = []
    window_table_lines: list[str] = []
    omission_lines: list[str] = []
    for key, label in window_names.items():
        window = windows[key]
        selection = window["selection"]
        trace_run = window["trace_run"]
        analysis = window["analysis"]
        observation = analysis["event_trace_observation"]
        assessment = window["opportunity_assessment"]
        density = selection["release_density_segments_per_second"]
        density_text = (
            f"{float(density):.3f}/s" if density is not None else "zero-span"
        )
        window_contract_lines.append(
            f"- {label}: {selection['segment_count']:,} segments; release span "
            f"{selection['release_span_seconds']:.3f}s "
            f"({selection['release_epoch_min']:.3f} to "
            f"{selection['release_epoch_max']:.3f}, {density_text}); retained "
            f"{trace_run['stored_event_trace_rows']:,} / "
            f"{trace_run['full_run_event_count']:,} processed event rows "
            f"({observation['coverage_fraction']:.1%}) and "
            f"{trace_run['stored_decision_or_hold_trace_rows']:,} complete "
            "decision/hold rows."
        )
        window_table_lines.append(
            f"| {label} | {observation['coverage_fraction']:.1%} | "
            f"{assessment['event_observed_effective_width']:.3f} / "
            f"{assessment['event_observed_parallel_item_fraction']:.3f} | "
            f"{assessment['event_optimistic_effective_width_upper_bound']:.3f} / "
            f"{assessment['event_optimistic_parallel_item_fraction_upper_bound']:.3f} | "
            f"{assessment['decision_observed_effective_width']:.3f} / "
            f"{assessment['decision_observed_parallel_item_fraction']:.3f} | "
            f"{assessment['status']} |"
        )
        omission_lines.append(
            f"- {label}: optimistic event bounds include all "
            f"{observation['untraced_event_count']:,} untraced processed rows "
            "as perfectly parallel work."
        )
    window_contract = "\n".join(window_contract_lines)
    window_table = "\n".join(window_table_lines)
    omission_notes = "\n".join(omission_lines)
    combined_note = (
        "Both tested windows definitively miss at least one required "
        "width/fraction gate, including the optimistic event upper bounds."
        if combined[
            "both_tested_windows_definitively_fail_any_required_width_or_fraction_gate"
        ]
        else "At least one tested window does not definitively miss the required "
        "width/fraction gates; this is only a bounded opportunity signal."
    )
    deployment_note = (
        "This result supports only offline batch work across mutually independent "
        "runtime jobs or simulator instances. It does not implement order-stream "
        "routing and does not authorize parallel execution as the default for one "
        "latency-sensitive live stream."
        if throughput["status"] == "GO_BATCH_THROUGHPUT_ONLY"
        else "Parallel promotion still applies only to mutually independent runtime instances."
    )
    return f"""# G4IRSF25 S4 parallel probe

## Decision

- **Same-stream node-parallel: {decision_row['same_stream_node_parallel']}**
- **Two independent S4 runs in ThreadPool: {decision_row['independent_run_parallel_throughput']}**
- Deployment scope: **{decision_row['independent_run_deployment_scope']}**
- The measured speedup is **offline/batch aggregate throughput across independent complete simulations, not a default for one live order stream**.

## Exact evidence contract

- Controller: `A0+S4+J2+E2`
- Throughput lifecycle segments: {payload['protocol']['lifecycle']['segment_count']:,}
- Release trace: `{payload['protocol']['lifecycle']['release_csv']}`
- Release binary: `{payload['protocol']['binary']['path']}`
- Release binary size: {payload['protocol']['binary']['size_bytes']:,} bytes
{window_contract}

The second canary is selected deterministically from the full exact-release
lifecycle: sort by `(release_epoch, segment_id, canonical ordinal)`, scan every
contiguous {window_size}-row window, minimize release span, and resolve ties by segment
ID/ordinal.

## Same-stream opportunity

Events were grouped by `(time, reconstructed E4 microphase)`.  A work item may
share a wave only when its conservative node footprint is disjoint.  The
footprint includes current node, edge endpoints, and linked candidate
downstream nodes; unknown and fault/repair work is a global barrier.

| Window | Event coverage | Event observed width / fraction | Event optimistic upper width / fraction | Decision width / fraction | Window result |
|---|---:|---:|---:|---:|---|
{window_table}

{omission_notes}

The prefix result is scoped as `NO_GO_ON_PREFIX_{window_size}_CANARY` when it misses the
gates; it is not a universal same-stream result.  Combining the prefix with
the deterministic peak-density window yields **{combined['status']}**.
{combined_note}

This is a feasibility audit. The active S4 runtime still executes one serial event loop,
and the current recommendation remains **defer implementation**.
These two {window_size}-segment windows cannot be extrapolated to a larger map or a new
workload. A same-stream implementation would need immutable phase
snapshots, node-footprint staging, validation, and deterministic commit in the
original `(time, microphase, seq)` order. Assigning one mutable policy object
to each node without that commit barrier is unsafe because corridors, J2, and
PIBT cross node boundaries.

## Independent-run throughput

| Mode | Aggregate events/s | Aggregate wall (s) | Median pair wall (s) | Median individual wall (s) | Median overlap |
|---|---:|---:|---:|---:|---:|
| Sequential | {sequential['aggregate_events_per_wall_second']:.1f} | {sequential['aggregate_wall_seconds']:.3f} | {sequential['median_pair_wall_seconds']:.3f} | {sequential['median_individual_wall_seconds']:.3f} | {sequential['median_overlap_factor']:.3f} |
| ThreadPool(2) | {parallel['aggregate_events_per_wall_second']:.1f} | {parallel['aggregate_wall_seconds']:.3f} | {parallel['median_pair_wall_seconds']:.3f} | {parallel['median_individual_wall_seconds']:.3f} | {parallel['median_overlap_factor']:.3f} |

- Aggregate speedup: **{throughput['aggregate_speedup']:.3f}x**
- Batch throughput gate: `>= {throughput['threshold']['parallel_aggregate_speedup_min']:.2f}x`
- Gate clearance: **{throughput['aggregate_speedup'] - throughput['threshold']['parallel_aggregate_speedup_min']:.3f}x**; treat this as a machine-local batch result, not a robust production margin.
- Parallel individual-wall regression: **{throughput['parallel_individual_wall_regression_fraction']:.1%}**
- Individual-wall latency guard: `<= {throughput['threshold']['parallel_individual_wall_regression_max']:.0%}` -> **{throughput['latency_guard_pass']}**
- Every run business/safety equivalent: **{throughput['equivalence_pass']}**
- Sequential lane order: `{throughput['sequential_lane_order']}`
- Pair mode order: `{throughput['mode_order']}`

## Recommended scheduling boundary

{deployment_note}

Keep a single live order stream serial until the phase-snapshot/staged-commit
design is implemented and revalidated against exact in-memory business and
safety projections.
"""


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--release-csv", type=Path, default=DEFAULT_RELEASE_CSV)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument(
        "--trace-segments", type=int, default=DEFAULT_TRACE_SEGMENTS
    )
    parser.add_argument(
        "--sequential-lane-order",
        choices=("alternating", "AB", "BA"),
        default="alternating",
    )
    parser.add_argument(
        "--mode-order",
        choices=("alternating", "sequential-first", "parallel-first"),
        default="alternating",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    binary = args.binary if args.binary is not None else _find_release_binary()
    payload = run_probe(
        binary=binary,
        release_csv=args.release_csv,
        rounds=args.rounds,
        trace_segments=args.trace_segments,
        sequential_lane_order=args.sequential_lane_order,
        mode_order=args.mode_order,
    )
    json_path = args.output_json if args.output_json.is_absolute() else ROOT / args.output_json
    csv_path = args.output_csv if args.output_csv.is_absolute() else ROOT / args.output_csv
    report_path = (
        args.output_report
        if args.output_report.is_absolute()
        else ROOT / args.output_report
    )
    _write(
        json_path,
        (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            + "\n"
        ).encode("utf-8"),
    )
    _write(csv_path, _csv_bytes(payload))
    _write(report_path, _report(payload).encode("utf-8"))
    print(
        json.dumps(
            {
                "status": "PASS",
                "same_stream_node_parallel": payload["decision"][
                    "same_stream_node_parallel"
                ],
                "independent_run_parallel_throughput": payload["decision"][
                    "independent_run_parallel_throughput"
                ],
                "aggregate_speedup": payload["independent_runs"][
                    "aggregate_speedup"
                ],
                "parallel_individual_wall_regression_fraction": payload[
                    "independent_runs"
                ]["parallel_individual_wall_regression_fraction"],
                "latency_guard_pass": payload["independent_runs"][
                    "latency_guard_pass"
                ],
                "json": str(json_path),
                "csv": str(csv_path),
                "report": str(report_path),
            },
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
