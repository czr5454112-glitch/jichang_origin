#!/usr/bin/env python3
"""Build the minimal G22 2x gap ledger and congestion-episode descriptors.

The runner deliberately reuses the existing G19 S4/J2/E2 native request and
G10's distribution-preserving 2x task artifact.  v2-safe is an offline
comparator only.  Its routes, reservations, and future state never enter an
S4 request or an episode descriptor.

The matched time bank is intentionally small::

    total_delta
      = source_wait_delta
      + inclusive_route_wait_delta
      + coordination_residual_delta

``merge_grant_wait_seconds`` is already a subset of S4's native junction wait.
It is published as a diagnostic and is never added again.  The v2 runtime has
no equivalent J2 merge-wait instrument, so a cross-runtime merge delta remains
``None`` rather than being fabricated as zero.

``describe_congestion_episodes`` is a pure threshold/hysteresis function.  It
accepts compact rows from a later native action census; importing this module
does not load the native extension or start a simulation.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))


RAW_CACHE_SCHEMA = "czr005.g4irsf22.gap_raw_cache.v1"
LEDGER_SCHEMA = "czr005.g4irsf22.gap_ledger.v1"
EPISODE_SCHEMA = "czr005.g4irsf22.congestion_episode.v1"
SCALE = 2

DEFAULT_CACHE = Path("outputs/runtime/g4irsf22_gap_episodes/2x_raw_cache.json")
DEFAULT_SEGMENTS = Path("outputs/tables/g4irsf22_gap_segment_ledger.csv")
DEFAULT_TASKS = Path("outputs/tables/g4irsf22_gap_task_ledger.csv")
DEFAULT_SUMMARY = Path("outputs/tables/g4irsf22_gap_ledger.json")
DEFAULT_BY_LEG = Path("outputs/tables/g4irsf22_gap_by_leg.csv")
DEFAULT_BY_SOURCE_TIME = Path("outputs/tables/g4irsf22_gap_by_source_time.csv")
DEFAULT_BY_HOTSPOT_TIME_LEG = Path(
    "outputs/tables/g4irsf22_gap_by_hotspot_time_leg.csv"
)
DEFAULT_GAP_REPORT = Path("outputs/reports/g4irsf22_coordination_gap_ledger.md")
DEFAULT_EPISODES = Path("outputs/tables/g4irsf22_congestion_episodes.json")
DEFAULT_EPISODE_STATUS = Path("outputs/tables/g4irsf22_gap_episode_status.json")
DEFAULT_EPISODE_REPORT = Path("outputs/reports/g4irsf22_episode_evidence.md")

TOLERANCE_SECONDS = 1.0e-7
ADDITIVE_FIELDS = (
    "total_seconds",
    "source_wait_seconds",
    "route_wait_inclusive_seconds",
    "coordination_residual_seconds",
)
DIAGNOSTIC_FIELDS = (
    "network_seconds",
    "merge_wait_diagnostic_seconds",
)


class GapEpisodeError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GapEpisodeError(message)


def _finite(value: Any, field: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{field} must be finite",
    )
    return float(value)


def _optional_finite(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    return _finite(value, field)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=TOLERANCE_SECONDS)


def _first(row: Mapping[str, Any], names: Sequence[str], field: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    raise GapEpisodeError(f"{field} is missing ({'/'.join(names)})")


def _optional_first(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _completed(row: Mapping[str, Any]) -> bool:
    for name in ("completed", "complete", "goal_reached"):
        if name in row:
            return row[name] is True
    return False


def _index_rows(
    rows: Sequence[Mapping[str, Any]], label: str
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        _require(isinstance(row, Mapping), f"{label}[{index}] is not an object")
        segment_id = row.get("segment_id")
        _require(
            isinstance(segment_id, str) and bool(segment_id),
            f"{label}[{index}] lacks segment_id",
        )
        _require(segment_id not in result, f"duplicate {label} segment: {segment_id}")
        result[segment_id] = row
    return result


def _normalized_outcome(
    runtime: str,
    protected: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize one completed S4 or v2 segment onto the release-time bank."""

    segment_id = str(protected["segment_id"])
    task_id = protected.get("task_id")
    _require(type(task_id) is int, f"{segment_id}: protected task_id must be int")
    _require(
        outcome.get("task_id") == task_id,
        f"{runtime}.{segment_id}: task identity mismatch",
    )
    _require(_completed(outcome), f"{runtime}.{segment_id}: segment is incomplete")

    release = _finite(protected.get("pass_time"), f"{segment_id}.pass_time")
    finish = _finite(outcome.get("finish_time"), f"{runtime}.{segment_id}.finish")

    if runtime == "s4":
        echoed_release = _optional_finite(
            outcome.get("release_time"), f"s4.{segment_id}.release_time"
        )
        if echoed_release is not None:
            _require(
                _close(echoed_release, release),
                f"s4.{segment_id}: release differs from protected input",
            )
        admitted = _finite(
            outcome.get("admitted_time"), f"s4.{segment_id}.admitted_time"
        )
        source_wait = admitted - release
        route_wait = _finite(
            _first(
                outcome,
                ("junction_queue_wait_seconds", "junction_wait_seconds"),
                f"s4.{segment_id}.route_wait",
            ),
            f"s4.{segment_id}.route_wait",
        )
        merge_wait = _finite(
            _first(
                outcome,
                ("merge_grant_wait_seconds", "merge_wait_seconds"),
                f"s4.{segment_id}.merge_wait",
            ),
            f"s4.{segment_id}.merge_wait",
        )
        merge_observed = True
    elif runtime == "v2":
        attempt = _finite(
            outcome.get("attempt_time"), f"v2.{segment_id}.attempt_time"
        )
        _require(
            _close(attempt, release),
            f"v2.{segment_id}: attempt differs from the shared G10 input",
        )
        source_wait = _finite(
            _first(
                outcome,
                ("source_wait_seconds",),
                f"v2.{segment_id}.source_wait",
            ),
            f"v2.{segment_id}.source_wait",
        )
        total_wait = _finite(
            _first(outcome, ("wait_seconds",), f"v2.{segment_id}.wait"),
            f"v2.{segment_id}.wait",
        )
        route_wait = total_wait - source_wait
        admitted = attempt + source_wait
        raw_merge = _optional_first(
            outcome, ("merge_grant_wait_seconds", "merge_wait_seconds")
        )
        merge_wait = _optional_finite(raw_merge, f"v2.{segment_id}.merge_wait")
        merge_observed = merge_wait is not None
    else:
        raise GapEpisodeError(f"unknown runtime: {runtime}")

    total = finish - release
    network = finish - admitted
    for name, value in (
        ("total", total),
        ("source wait", source_wait),
        ("network", network),
        ("route wait", route_wait),
    ):
        _require(value >= -TOLERANCE_SECONDS, f"{runtime}.{segment_id}: negative {name}")
    source_wait = max(0.0, source_wait)
    network = max(0.0, network)
    route_wait = max(0.0, route_wait)
    _require(
        route_wait <= network + TOLERANCE_SECONDS,
        f"{runtime}.{segment_id}: inclusive route wait exceeds network time",
    )
    if merge_wait is not None:
        _require(merge_wait >= 0.0, f"{runtime}.{segment_id}: negative merge wait")
        _require(
            merge_wait <= route_wait + TOLERANCE_SECONDS,
            f"{runtime}.{segment_id}: merge wait is not a route-wait subset",
        )

    coordination_residual = total - source_wait - route_wait
    _require(
        coordination_residual >= -TOLERANCE_SECONDS,
        f"{runtime}.{segment_id}: negative coordination residual",
    )
    coordination_residual = max(0.0, coordination_residual)
    _require(
        _close(total, source_wait + route_wait + coordination_residual),
        f"{runtime}.{segment_id}: time bank does not reconstruct total",
    )
    _require(
        _close(total, source_wait + network),
        f"{runtime}.{segment_id}: source plus network does not reconstruct total",
    )
    return {
        "total_seconds": total,
        "source_wait_seconds": source_wait,
        "network_seconds": network,
        "route_wait_inclusive_seconds": route_wait,
        "merge_wait_diagnostic_seconds": merge_wait,
        "merge_wait_observed": merge_observed,
        "coordination_residual_seconds": coordination_residual,
    }


def _delta(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else left - right


def build_matched_ledgers(
    input_rows: Sequence[Mapping[str, Any]],
    s4_rows: Sequence[Mapping[str, Any]],
    v2_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return exact segment/task ledgers matched by immutable IDs.

    Deltas are always ``S4 - v2`` in seconds.  This function performs no I/O.
    """

    protected = _index_rows(input_rows, "input")
    s4 = _index_rows(s4_rows, "s4")
    v2 = _index_rows(v2_rows, "v2")
    expected = set(protected)
    _require(set(s4) == expected, "S4 segment set differs from the shared input")
    _require(set(v2) == expected, "v2 segment set differs from the shared input")

    order = sorted(
        expected,
        key=lambda segment_id: (
            int(protected[segment_id]["task_id"]),
            float(protected[segment_id]["pass_time"]),
            segment_id,
        ),
    )
    segment_ledger: list[dict[str, Any]] = []
    for segment_id in order:
        source = protected[segment_id]
        s4_value = _normalized_outcome("s4", source, s4[segment_id])
        v2_value = _normalized_outcome("v2", source, v2[segment_id])
        row: dict[str, Any] = {
            "segment_id": segment_id,
            "task_id": int(source["task_id"]),
            "leg": str(source.get("leg", "direct")),
            "source": str(source.get("source", f"node_{source.get('start', '')}")),
            "start": source.get("start"),
            "goal": source.get("goal"),
            "release_time": float(source["pass_time"]),
            "release_time_block": int(float(source["pass_time"]) // 3600.0),
            "original_entry_time": source.get("original_entry_time"),
        }
        for field in (*ADDITIVE_FIELDS, *DIAGNOSTIC_FIELDS):
            row[f"s4_{field}"] = s4_value[field]
            row[f"v2_{field}"] = v2_value[field]
            row[f"delta_{field}"] = _delta(s4_value[field], v2_value[field])
        row["s4_merge_wait_observed"] = s4_value["merge_wait_observed"]
        row["v2_merge_wait_observed"] = v2_value["merge_wait_observed"]
        row["coordination_residual_delta_seconds"] = row[
            "delta_coordination_residual_seconds"
        ]
        _require(
            _close(
                float(row["delta_total_seconds"]),
                float(row["delta_source_wait_seconds"])
                + float(row["delta_route_wait_inclusive_seconds"])
                + float(row["coordination_residual_delta_seconds"]),
            ),
            f"{segment_id}: matched delta bank does not reconstruct",
        )
        segment_ledger.append(row)

    task_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in segment_ledger:
        task_groups[int(row["task_id"])].append(row)
    task_ledger: list[dict[str, Any]] = []
    for task_id in sorted(task_groups):
        members = task_groups[task_id]
        legs = sorted({str(row["leg"]) for row in members})
        task: dict[str, Any] = {
            "task_id": task_id,
            "segment_count": len(members),
            "segment_ids": [str(row["segment_id"]) for row in members],
            "leg": legs[0] if len(legs) == 1 else "mixed",
            "legs": legs,
            "source": members[0]["source"],
            "release_time_block": int(float(members[0]["release_time"]) // 3600.0),
        }
        for field in (*ADDITIVE_FIELDS, "network_seconds"):
            for prefix in ("s4", "v2", "delta"):
                task[f"{prefix}_{field}"] = sum(
                    float(row[f"{prefix}_{field}"]) for row in members
                )
        for prefix in ("s4", "v2"):
            merge_values = [
                row[f"{prefix}_merge_wait_diagnostic_seconds"] for row in members
            ]
            task[f"{prefix}_merge_wait_diagnostic_seconds"] = (
                sum(float(value) for value in merge_values)
                if all(value is not None for value in merge_values)
                else None
            )
            task[f"{prefix}_merge_wait_observed"] = all(
                bool(row[f"{prefix}_merge_wait_observed"]) for row in members
            )
        task["delta_merge_wait_diagnostic_seconds"] = _delta(
            task["s4_merge_wait_diagnostic_seconds"],
            task["v2_merge_wait_diagnostic_seconds"],
        )
        task["coordination_residual_delta_seconds"] = task[
            "delta_coordination_residual_seconds"
        ]
        _require(
            _close(
                float(task["delta_total_seconds"]),
                float(task["delta_source_wait_seconds"])
                + float(task["delta_route_wait_inclusive_seconds"])
                + float(task["coordination_residual_delta_seconds"]),
            ),
            f"task {task_id}: matched delta bank does not reconstruct",
        )
        task_ledger.append(task)

    def mean(field: str) -> float | None:
        return (
            sum(float(row[field]) for row in task_ledger) / len(task_ledger)
            if task_ledger
            else None
        )

    summary = {
        "schema": LEDGER_SCHEMA,
        "status": "COMPLETE" if task_ledger else "EMPTY",
        "scale": SCALE,
        "delta_direction": "S4_MINUS_V2",
        "denominator": "java_release_time_tth",
        "segment_count": len(segment_ledger),
        "task_count": len(task_ledger),
        "mean_gap_seconds_per_task": mean("delta_total_seconds"),
        "mean_source_wait_delta_seconds": mean("delta_source_wait_seconds"),
        "mean_route_wait_inclusive_delta_seconds": mean(
            "delta_route_wait_inclusive_seconds"
        ),
        "mean_coordination_residual_delta_seconds": mean(
            "coordination_residual_delta_seconds"
        ),
        "mean_network_delta_seconds": mean("delta_network_seconds"),
        "additive_identity": (
            "delta_total_seconds = delta_source_wait_seconds + "
            "delta_route_wait_inclusive_seconds + "
            "coordination_residual_delta_seconds"
        ),
        "merge_semantics": (
            "merge_wait is a diagnostic subset of inclusive route wait and is "
            "never added to the time bank; v2 has no equivalent J2 instrument"
        ),
        "coordination_residual_semantics": (
            "arithmetic remainder after measured source and inclusive route wait; "
            "it includes motion/service and uninstrumented coordination, so it is "
            "not by itself a causal coordination estimate"
        ),
        "runtime_boundary": (
            "v2-safe is an offline comparator; no v2 route, reservation, or future "
            "state is a runtime feature"
        ),
    }
    return {
        "schema": LEDGER_SCHEMA,
        "summary": summary,
        "segment_rows": segment_ledger,
        "task_rows": task_ledger,
    }


def aggregate_gap_rows(
    rows: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in keys)].append(row)
    output: list[dict[str, Any]] = []
    for identity, members in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        result = {key: value for key, value in zip(keys, identity, strict=True)}
        result["row_count"] = len(members)
        for field in (
            "delta_total_seconds",
            "delta_source_wait_seconds",
            "delta_route_wait_inclusive_seconds",
            "coordination_residual_delta_seconds",
            "delta_network_seconds",
        ):
            values = [float(row[field]) for row in members]
            result[f"mean_{field}"] = sum(values) / len(values)
        result["s4_slower_fraction"] = sum(
            float(row["delta_total_seconds"]) > 0.0 for row in members
        ) / len(members)
        output.append(result)
    return output


def render_gap_report(
    summary: Mapping[str, Any],
    by_leg: Sequence[Mapping[str, Any]],
    by_source_time: Sequence[Mapping[str, Any]],
    by_hotspot_time_leg: Sequence[Mapping[str, Any]],
) -> str:
    top = sorted(
        by_source_time,
        key=lambda row: float(row["mean_delta_total_seconds"]),
        reverse=True,
    )[:8]
    lines = [
        "# G4IRSF22 matched 2x coordination-gap ledger",
        "",
        "Status: `COMPLETE` on the same 57,012 raw bags / 87,206 runtime segments.",
        "",
        "## Additive time bank (S4 minus v2-safe)",
        "",
        f"- Total gap: `{float(summary['mean_gap_seconds_per_task']):.6f}` s/raw bag.",
        f"- Source: `{float(summary['mean_source_wait_delta_seconds']):.6f}` s/raw bag.",
        f"- Inclusive route wait: `{float(summary['mean_route_wait_inclusive_delta_seconds']):.6f}` s/raw bag.",
        f"- Arithmetic residual: `{float(summary['mean_coordination_residual_delta_seconds']):.6f}` s/raw bag.",
        f"- Network diagnostic: `{float(summary['mean_network_delta_seconds']):.6f}` s/raw bag.",
        "",
        "The residual includes motion, service, and uninstrumented coordination. It is not named a pure coordination causal effect. Merge wait is a diagnostic subset of route wait and is never added twice; v2 has no equivalent J2 merge-grant instrument.",
        "",
        "## Segment leg diagnostic",
        "",
        "These rows are segment-weighted diagnostics; they do not share the "
        "raw-bag denominator of the additive time bank above.",
        "",
        "| Leg | Segments | Mean total delta (s) | Mean source delta (s) | Mean route-wait delta (s) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in by_leg:
        lines.append(
            f"| {row['leg']} | {int(row['row_count']):,} | "
            f"{float(row['mean_delta_total_seconds']):.6f} | "
            f"{float(row['mean_delta_source_wait_seconds']):.6f} | "
            f"{float(row['mean_delta_route_wait_inclusive_seconds']):.6f} |"
        )
    lines.extend(
        [
            "",
            "## Largest raw-task origin source/time-block gaps",
            "",
            "`Source` here is the raw task's first-segment/origin source. It must "
            "not be read as the later storage_out admission node.",
            "",
            "| Origin source | Release block | Raw bags | Mean total delta (s) | S4-slower fraction |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in top:
        lines.append(
            f"| {row['source']} | {row['release_time_block']} | "
            f"{int(row['row_count']):,} | "
            f"{float(row['mean_delta_total_seconds']):.6f} | "
            f"{float(row['s4_slower_fraction']):.3f} |"
        )
    storage_out_confirmation = sorted(
        (
            row
            for row in by_hotspot_time_leg
            if row["leg"] == "storage_out"
            and row["source"] == "node_52"
            and int(row["release_time_block"]) in {7, 8}
        ),
        key=lambda row: int(row["release_time_block"]),
    )
    lines.extend(
        [
            "",
            "## Storage-out admission seam (segment-level)",
            "",
            "The true `storage_out` admission seam is `node_52`: block 7 is "
            "the largest mean-total-gap cell, and block 8 confirms the same "
            "seam. The block-6 raw-task origin rows for `node_53`, `node_1`, "
            "`node_2`, and `node_0` above are not `storage_out` admissions.",
            "",
            "| Leg | Admission source | Release block | Segments | Mean total delta (s) | Mean source delta (s) | Mean route-wait delta (s) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in storage_out_confirmation:
        lines.append(
            f"| {row['leg']} | {row['source']} | "
            f"{int(row['release_time_block'])} | {int(row['row_count']):,} | "
            f"{float(row['mean_delta_total_seconds']):.6f} | "
            f"{float(row['mean_delta_source_wait_seconds']):.6f} | "
            f"{float(row['mean_delta_route_wait_inclusive_seconds']):.6f} |"
        )
    lines.extend(
        [
            "",
            "v2-safe remains an offline comparator only. No v2 route, reservation, or future state is exposed to the decentralized runtime.",
            "",
        ]
    )
    return "\n".join(lines)


def _episode_row(
    row: Mapping[str, Any], index: int, signal_field: str
) -> dict[str, Any]:
    owner = row.get("owner", row.get("node"))
    _require(owner is not None and not isinstance(owner, bool), f"episode row {index}: owner missing")
    time_seconds = _finite(
        row.get("time_seconds", row.get("event_time")),
        f"episode row {index}.time_seconds",
    )
    signal = _finite(row.get(signal_field), f"episode row {index}.{signal_field}")
    _require(signal >= 0.0, f"episode row {index}: negative signal")
    task_id = row.get("task_id")
    _require(task_id is None or type(task_id) is int, f"episode row {index}: bad task_id")
    segment_id = row.get("segment_id")
    _require(
        segment_id is None or isinstance(segment_id, str),
        f"episode row {index}: bad segment_id",
    )
    return {
        "source_row_index": index,
        "row_id": row.get("row_id", index),
        "owner": owner,
        "time_seconds": time_seconds,
        "signal": signal,
        "segment_id": segment_id,
        "task_id": task_id,
        "leg": str(row.get("leg", "unknown")),
        "upstream_branch": row.get("upstream_branch"),
        "s4_v2_diverged": row.get(
            "s4_v2_diverged", row.get("s4_v2_divergence", False)
        )
        is True,
        "merge_winner_changed": row.get("merge_winner_changed", False) is True,
        "incoming_eta_count": _optional_finite(
            row.get("incoming_eta_count"), f"episode row {index}.incoming_eta_count"
        ),
        "service_rate": _optional_finite(
            row.get("service_rate"), f"episode row {index}.service_rate"
        ),
    }


def _episode_descriptor(
    rows: Sequence[Mapping[str, Any]],
    *,
    ordinal: int,
    enter_threshold: float,
    exit_threshold: float,
    time_block_seconds: float,
    signal_field: str,
    closed: bool,
) -> dict[str, Any]:
    start = rows[0]
    end = rows[-1]
    peak = max(rows, key=lambda row: (float(row["signal"]), -int(row["source_row_index"])))
    peak_delay = float(peak["time_seconds"]) - float(start["time_seconds"])
    slope = (
        (float(peak["signal"]) - float(start["signal"])) / peak_delay
        if peak_delay > 0.0
        else 0.0
    )
    legs = sorted({str(row["leg"]) for row in rows})
    branches = sorted(
        {str(row["upstream_branch"]) for row in rows if row["upstream_branch"] is not None}
    )
    incoming = [
        float(row["incoming_eta_count"])
        for row in rows
        if row["incoming_eta_count"] is not None
    ]
    service = [
        float(row["service_rate"])
        for row in rows
        if row["service_rate"] is not None
    ]
    affected = [
        {
            "row_index": int(row["source_row_index"]),
            "row_id": row["row_id"],
            "segment_id": row["segment_id"],
            "task_id": row["task_id"],
        }
        for row in rows
    ]
    owner = start["owner"]
    return {
        "schema": EPISODE_SCHEMA,
        "episode_id": f"{owner}|{ordinal}|{start['source_row_index']}",
        "owner": owner,
        "time_block": int(float(start["time_seconds"]) // time_block_seconds),
        "leg": legs[0] if len(legs) == 1 else "mixed",
        "legs": legs,
        "start": {
            "time_seconds": float(start["time_seconds"]),
            "queue_value": float(start["signal"]),
            "row_index": int(start["source_row_index"]),
        },
        "peak": {
            "time_seconds": float(peak["time_seconds"]),
            "queue_value": float(peak["signal"]),
            "row_index": int(peak["source_row_index"]),
        },
        "end": {
            "time_seconds": float(end["time_seconds"]),
            "queue_value": float(end["signal"]),
            "row_index": int(end["source_row_index"]),
        },
        "closed": closed,
        "signal_field": signal_field,
        "enter_threshold": enter_threshold,
        "exit_threshold": exit_threshold,
        "queue_slope_to_peak_per_second": slope,
        "incoming_eta_peak": max(incoming) if incoming else None,
        "mean_service_rate": sum(service) / len(service) if service else None,
        "s4_v2_divergence_row_count": sum(
            1 for row in rows if row["s4_v2_diverged"]
        ),
        "merge_winner_change_row_count": sum(
            1 for row in rows if row["merge_winner_changed"]
        ),
        "upstream_branches": branches,
        "affected_row_count": len(affected),
        "affected_rows": affected,
    }


def describe_congestion_episodes(
    rows: Sequence[Mapping[str, Any]],
    *,
    enter_threshold: float,
    exit_threshold: float,
    time_block_seconds: float = 3600.0,
    signal_field: str = "queue_length",
) -> list[dict[str, Any]]:
    """Describe per-owner congestion episodes without mutating inputs or doing I/O.

    An episode starts at ``signal >= enter_threshold`` and closes at the first
    later row with ``signal <= exit_threshold``.  An episode still active at the
    end of the supplied census is returned with ``closed=False``.
    """

    enter = _finite(enter_threshold, "enter_threshold")
    exit_ = _finite(exit_threshold, "exit_threshold")
    block = _finite(time_block_seconds, "time_block_seconds")
    _require(enter > exit_ >= 0.0, "thresholds require enter > exit >= 0")
    _require(block > 0.0, "time_block_seconds must be positive")
    _require(bool(signal_field), "signal_field must be nonempty")

    by_owner: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        normalized = _episode_row(row, index, signal_field)
        owner_key = (type(normalized["owner"]).__name__, str(normalized["owner"]))
        by_owner[owner_key].append(normalized)

    episodes: list[dict[str, Any]] = []
    for owner_key in sorted(by_owner):
        owner_rows = sorted(
            by_owner[owner_key],
            key=lambda row: (float(row["time_seconds"]), int(row["source_row_index"])),
        )
        active: list[dict[str, Any]] = []
        ordinal = 0
        for row in owner_rows:
            if not active:
                if float(row["signal"]) >= enter:
                    active = [row]
                continue
            active.append(row)
            if float(row["signal"]) <= exit_:
                episodes.append(
                    _episode_descriptor(
                        active,
                        ordinal=ordinal,
                        enter_threshold=enter,
                        exit_threshold=exit_,
                        time_block_seconds=block,
                        signal_field=signal_field,
                        closed=True,
                    )
                )
                ordinal += 1
                active = []
        if active:
            episodes.append(
                _episode_descriptor(
                    active,
                    ordinal=ordinal,
                    enter_threshold=enter,
                    exit_threshold=exit_,
                    time_block_seconds=block,
                    signal_field=signal_field,
                    closed=False,
                )
            )
    return episodes


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _consistent_candidate_value(
    observations: Sequence[Mapping[str, Any]], field: str, row_number: int
) -> float:
    values = [
        _finite(observation.get(field), f"census row {row_number}.{field}")
        for observation in observations
    ]
    _require(
        all(_close(values[0], value) for value in values[1:]),
        f"census row {row_number}: candidate copies disagree on current {field}",
    )
    return values[0]


def stream_route_census_episode_rows(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stream a G22 Route census into compact current-owner signal rows.

    ``junction_queue_length`` and ``priority_local_contention`` are current
    junction observations copied into every candidate record.  Candidate
    agreement is required before the shared value is accepted.  The episode
    signal is their maximum; target queue fields are deliberately excluded.
    """

    compact: list[dict[str, Any]] = []
    legs: Counter[str] = Counter()
    owners: Counter[str] = Counter()
    signals: list[float] = []
    queue_values: list[float] = []
    contention_values: list[float] = []
    with path.open("r", encoding="utf-8") as handle:
        for row_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GapEpisodeError(
                    f"census row {row_number}: invalid JSON: {exc.msg}"
                ) from exc
            _require(isinstance(row, Mapping), f"census row {row_number}: non-object")
            observations = row.get("candidate_observations")
            _require(
                isinstance(observations, list)
                and bool(observations)
                and all(isinstance(value, Mapping) for value in observations),
                f"census row {row_number}: candidate_observations missing",
            )
            queue = _consistent_candidate_value(
                observations, "junction_queue_length", row_number
            )
            contention = _consistent_candidate_value(
                observations, "priority_local_contention", row_number
            )
            signal = max(queue, contention)
            segment_id = row.get("segment_id")
            _require(
                isinstance(segment_id, str) and bool(segment_id),
                f"census row {row_number}: segment_id missing",
            )
            parts = segment_id.split(":")
            leg = parts[1] if len(parts) >= 2 and parts[1] else "unknown"
            owner = row.get("current_node")
            _require(type(owner) is int, f"census row {row_number}: current_node missing")
            event_ordinal = row.get("event_ordinal")
            _require(
                type(event_ordinal) is int and event_ordinal >= 0,
                f"census row {row_number}: event_ordinal invalid",
            )
            compact.append(
                {
                    "row_id": event_ordinal,
                    "owner": owner,
                    "time_seconds": _finite(
                        row.get("event_time"), f"census row {row_number}.event_time"
                    ),
                    "local_contention_signal": signal,
                    "junction_queue_length": queue,
                    "priority_local_contention": contention,
                    "segment_id": segment_id,
                    "task_id": row.get("task_id"),
                    "leg": leg,
                }
            )
            signals.append(signal)
            queue_values.append(queue)
            contention_values.append(contention)
            owners[str(owner)] += 1
            legs[leg] += 1

    _require(bool(compact), f"empty Route census: {path}")

    def distribution(values: Sequence[float]) -> dict[str, float | None]:
        return {
            "min": min(values),
            "p50": _quantile(values, 0.50),
            "p75": _quantile(values, 0.75),
            "p90": _quantile(values, 0.90),
            "p95": _quantile(values, 0.95),
            "p99": _quantile(values, 0.99),
            "max": max(values),
        }

    audit = {
        "sampling_basis": "route_decision_sampled",
        "row_count": len(compact),
        "owner_row_counts": dict(sorted(owners.items(), key=lambda item: int(item[0]))),
        "leg_row_counts": dict(sorted(legs.items())),
        "candidate_current_field_consistency": "PASS",
        "signal_definition": (
            "max(candidate-consistent current junction_queue_length, "
            "candidate-consistent current priority_local_contention)"
        ),
        "target_candidate_queue_fields_used": False,
        "signal_distribution": distribution(signals),
        "junction_queue_length_distribution": distribution(queue_values),
        "priority_local_contention_distribution": distribution(contention_values),
    }
    return compact, audit


def _compact_affected_rows(
    episodes: Sequence[Mapping[str, Any]], limit: int
) -> list[dict[str, Any]]:
    _require(limit >= 3, "affected-row limit must be at least 3")
    result: list[dict[str, Any]] = []
    for original in episodes:
        episode = dict(original)
        affected = list(episode.get("affected_rows", []))
        total = len(affected)
        if total > limit:
            indices = sorted(
                {
                    int(round(index * (total - 1) / (limit - 1)))
                    for index in range(limit)
                }
            )
            episode["affected_rows"] = [affected[index] for index in indices]
            episode["affected_rows_truncated"] = True
        else:
            episode["affected_rows"] = affected
            episode["affected_rows_truncated"] = False
        episode["affected_row_count"] = total
        episode["affected_rows_retained"] = len(episode["affected_rows"])
        result.append(episode)
    return result


def analyze_route_census_episodes(
    path: Path,
    *,
    enter_threshold: float,
    exit_threshold: float,
    time_block_seconds: float = 3600.0,
    affected_row_limit: int = 64,
) -> dict[str, Any]:
    compact_rows, audit = stream_route_census_episode_rows(path)
    episodes = describe_congestion_episodes(
        compact_rows,
        enter_threshold=enter_threshold,
        exit_threshold=exit_threshold,
        time_block_seconds=time_block_seconds,
        signal_field="local_contention_signal",
    )
    episodes = _compact_affected_rows(episodes, affected_row_limit)
    owner_values = sorted({episode["owner"] for episode in episodes})
    time_blocks = sorted({int(episode["time_block"]) for episode in episodes})
    leg_values = sorted(
        {leg for episode in episodes for leg in episode.get("legs", [])}
    )
    return {
        "schema": EPISODE_SCHEMA,
        "status": "DETECTION_COMPLETE",
        "sampling_basis": "route_decision_sampled",
        "claim_boundary": (
            "Episodes are reconstructed from multi-action Route decision samples, "
            "not continuous queue telemetry; start/end are first sampled crossings."
        ),
        "source": str(path),
        "signal_audit": audit,
        "thresholds": {
            "enter": float(enter_threshold),
            "exit": float(exit_threshold),
            "hysteresis": True,
            "rationale": (
                "enter at at least 16 local queued/contending bags and exit at at "
                "most 8; the two-to-one band suppresses decision-sample jitter"
                if _close(float(enter_threshold), 16.0)
                and _close(float(exit_threshold), 8.0)
                else "explicit caller-provided local-contention thresholds"
            ),
        },
        "coverage": {
            "episode_count": len(episodes),
            "closed_episode_count": sum(1 for row in episodes if row["closed"]),
            "open_at_census_end_count": sum(1 for row in episodes if not row["closed"]),
            "owner_count": len(owner_values),
            "owners": owner_values,
            "time_block_count": len(time_blocks),
            "time_blocks": time_blocks,
            "leg_count": len(leg_values),
            "legs": leg_values,
        },
        "affected_row_retention_limit_per_episode": affected_row_limit,
        "episodes": episodes,
    }


def _episode_markdown(artifact: Mapping[str, Any]) -> str:
    coverage = artifact["coverage"]
    thresholds = artifact["thresholds"]
    audit = artifact["signal_audit"]
    distribution = audit["signal_distribution"]
    lines = [
        "# G4IRSF22 congestion episode evidence",
        "",
        f"Status: `{artifact['status']}`.",
        "",
        "These are **route-decision-sampled** congestion episodes, not continuous "
        "queue telemetry. Start, peak, and end denote sampled Route decisions.",
        "",
        "## Signal and hysteresis",
        "",
        f"- Signal: `{audit['signal_definition']}`.",
        f"- Enter/exit: `{thresholds['enter']:g}` / `{thresholds['exit']:g}`.",
        f"- Rationale: {thresholds['rationale']}.",
        "- Candidate target queues and any future/global information are excluded.",
        f"- Census rows: `{audit['row_count']:,}`; candidate-current consistency: "
        f"`{audit['candidate_current_field_consistency']}`.",
        f"- Signal p50/p90/p95/p99/max: `{distribution['p50']:.3f}` / "
        f"`{distribution['p90']:.3f}` / `{distribution['p95']:.3f}` / "
        f"`{distribution['p99']:.3f}` / `{distribution['max']:.3f}`.",
        "",
        "## Coverage",
        "",
        f"- Episodes: `{coverage['episode_count']}` "
        f"(`{coverage['closed_episode_count']}` closed, "
        f"`{coverage['open_at_census_end_count']}` open at census end).",
        f"- Owners: `{coverage['owner_count']}` — "
        f"`{', '.join(str(value) for value in coverage['owners'])}`.",
        f"- Time blocks: `{coverage['time_block_count']}` — "
        f"`{', '.join(str(value) for value in coverage['time_blocks'])}`.",
        f"- Legs: `{coverage['leg_count']}` — "
        f"`{', '.join(coverage['legs'])}`.",
        "",
        "Each descriptor retains owner, start/peak/end, time block, leg coverage, "
        "queue slope, and a bounded sample of affected Route rows. "
        "`affected_row_count` always records the full sampled count.",
        "Affected rows are sampled decisions, not independent bags. A closed "
        "sampled episode does not prove that a continuously observed physical "
        "queue emptied, and the 16/8 episodes are descriptive rather than "
        "independent causal units.",
        "",
    ]
    return "\n".join(lines)


def make_raw_cache(
    input_rows: Sequence[Mapping[str, Any]],
    s4_rows: Sequence[Mapping[str, Any]],
    v2_rows: Sequence[Mapping[str, Any]],
    *,
    input_descriptor: Mapping[str, Any] | None = None,
    s4_summary: Mapping[str, Any] | None = None,
    v2_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the phase boundary consumed by :func:`analyze_raw_cache`."""

    cache = {
        "schema": RAW_CACHE_SCHEMA,
        "scale": SCALE,
        "input": dict(input_descriptor or {}),
        "runtime_boundary": {
            "s4": "A0+S4+J2+E2 native one-hop runtime",
            "v2": "offline comparator only",
        },
        "input_rows": [dict(row) for row in input_rows],
        "s4": {"summary": dict(s4_summary or {}), "segment_rows": [dict(row) for row in s4_rows]},
        "v2": {"summary": dict(v2_summary or {}), "segment_rows": [dict(row) for row in v2_rows]},
    }
    # Validate the phase boundary before a potentially large cache is written.
    build_matched_ledgers(cache["input_rows"], cache["s4"]["segment_rows"], cache["v2"]["segment_rows"])
    return cache


def analyze_raw_cache(
    cache: Mapping[str, Any],
    *,
    episode_rows: Sequence[Mapping[str, Any]] | None = None,
    enter_threshold: float | None = None,
    exit_threshold: float | None = None,
    time_block_seconds: float = 3600.0,
    signal_field: str = "queue_length",
) -> dict[str, Any]:
    _require(cache.get("schema") == RAW_CACHE_SCHEMA, "raw cache schema mismatch")
    _require(cache.get("scale") == SCALE, "raw cache is not the matched 2x case")
    input_rows = cache.get("input_rows")
    s4 = cache.get("s4")
    v2 = cache.get("v2")
    _require(isinstance(input_rows, list), "raw cache input_rows missing")
    _require(isinstance(s4, Mapping) and isinstance(s4.get("segment_rows"), list), "raw cache S4 rows missing")
    _require(isinstance(v2, Mapping) and isinstance(v2.get("segment_rows"), list), "raw cache v2 rows missing")
    ledger = build_matched_ledgers(input_rows, s4["segment_rows"], v2["segment_rows"])

    if episode_rows is None:
        episode_artifact = {
            "schema": EPISODE_SCHEMA,
            "status": "PENDING_ACTION_CENSUS",
            "episodes": [],
            "claim_boundary": "No queue census rows were supplied; no episodes were inferred from task outcomes.",
        }
    else:
        _require(
            enter_threshold is not None and exit_threshold is not None,
            "episode thresholds are required when census rows are supplied",
        )
        episodes = describe_congestion_episodes(
            episode_rows,
            enter_threshold=enter_threshold,
            exit_threshold=exit_threshold,
            time_block_seconds=time_block_seconds,
            signal_field=signal_field,
        )
        episode_artifact = {
            "schema": EPISODE_SCHEMA,
            "status": "DETECTION_COMPLETE",
            "episode_count": len(episodes),
            "episodes": episodes,
        }
    return {"ledger": ledger, "episode_artifact": episode_artifact}


def collect_same_origin_2x(*, root: Path, binary: Path) -> dict[str, Any]:
    """Run the existing S4/E2 and v2 implementations on one G10 2x artifact."""

    from scripts.eval import run_g4irsf10_v2_safe_scale_hardcase_training as g10
    from scripts.eval import run_g4irsf18_jit_campaign as g18_jit
    from scripts.eval import run_g4irsf19_bounded_capacity as g19
    from scripts.eval import run_g4irsf20_event_hotpath as g20
    from czr005 import cpp_backend

    task_path, task_metadata = g10.ensure_source_queue_for_case(
        scale=SCALE,
        rolling_days=1,
        time_compression=1.0,
        label="g4irsf19_bounded_capacity_2x",
    )
    rows, descriptor = g19.load_g18_scale_input(SCALE, root=root)
    _require(len(rows) == 87_206, "shared 2x input must contain 87,206 segments")

    request = g20.build_native_request(
        rows,
        scale=SCALE,
        policy="E2",
        binary=binary,
        root=root,
        bounded_wall_seconds=60.0,
        check_events=100_000,
    )
    s4_payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    _require(isinstance(s4_payload, Mapping), "S4 native result is not an object")
    s4_summary = s4_payload.get("summary")
    s4_rows = s4_payload.get("bags")
    _require(isinstance(s4_summary, Mapping), "S4 summary missing")
    _require(isinstance(s4_rows, list), "S4 segment rows missing")
    _require(g18_jit._hard_safety(s4_summary, len(rows))["pass"], "S4 hard-safety gate failed")

    v2_case = g10.RunCase(
        scenario="g4irsf22_gap_v2_safe_2x",
        task_path=task_path,
        scale="2x",
        claim_level="offline_comparator",
        generation_level="distribution_preserving_resample",
        note="G22 matched gap ledger; v2-safe never supplies runtime features",
    )
    v2_metrics, v2_result = g10.run_case(v2_case)
    _require(v2_result is not None, "v2 runtime returned no result")
    raw_task_count = len({int(row["task_id"]) for row in rows})
    _require(
        g10.stable_row(v2_metrics, expected_complete=raw_task_count),
        "v2 offline comparator failed completion/safety gates",
    )

    protected_projection = [
        {
            name: row[name]
            for name in (
                "segment_id",
                "task_id",
                "pass_time",
                "original_entry_time",
                "std",
                "start",
                "goal",
                "source",
                "leg",
            )
            if name in row
        }
        for row in rows
    ]
    return make_raw_cache(
        protected_projection,
        s4_rows,
        v2_result.tasks,
        input_descriptor={
            **dict(descriptor),
            "task_artifact": str(task_path),
            "generation_level": task_metadata.get("generation_level"),
            "release_semantics": task_metadata.get("release_semantics"),
        },
        s4_summary=s4_summary,
        v2_summary=v2_metrics,
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, Mapping):
        value = value.get("rows")
    _require(isinstance(value, list), f"{path}: expected JSON array or JSONL")
    _require(all(isinstance(row, Mapping) for row in value), f"{path}: non-object row")
    return [dict(row) for row in value]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if value is None:
        return ""
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in row:
            if name not in seen:
                seen.add(name)
                fieldnames.append(name)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _csv_value(row.get(name)) for name in fieldnames})


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", choices=("collect", "analyze", "episodes", "all"), default="analyze"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--segment-ledger", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--task-ledger", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--by-leg", type=Path, default=DEFAULT_BY_LEG)
    parser.add_argument("--by-source-time", type=Path, default=DEFAULT_BY_SOURCE_TIME)
    parser.add_argument(
        "--by-hotspot-time-leg", type=Path, default=DEFAULT_BY_HOTSPOT_TIME_LEG
    )
    parser.add_argument("--gap-report", type=Path, default=DEFAULT_GAP_REPORT)
    parser.add_argument("--episode-samples", type=Path)
    parser.add_argument("--route-census", type=Path)
    parser.add_argument("--episodes", type=Path)
    parser.add_argument("--episode-report", type=Path, default=DEFAULT_EPISODE_REPORT)
    parser.add_argument("--episode-enter-threshold", type=float)
    parser.add_argument("--episode-exit-threshold", type=float)
    parser.add_argument("--time-block-seconds", type=float, default=3600.0)
    parser.add_argument("--signal-field", default="queue_length")
    parser.add_argument("--affected-row-limit", type=int, default=64)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    cache_path = _rooted(root, args.cache)

    if args.stage == "episodes":
        _require(args.route_census is not None, "--route-census is required for episodes")
        _require(
            args.episode_enter_threshold is not None
            and args.episode_exit_threshold is not None,
            "episode thresholds are required for episodes",
        )
        artifact = analyze_route_census_episodes(
            _rooted(root, args.route_census),
            enter_threshold=args.episode_enter_threshold,
            exit_threshold=args.episode_exit_threshold,
            time_block_seconds=args.time_block_seconds,
            affected_row_limit=args.affected_row_limit,
        )
        episodes_path = _rooted(root, args.episodes or DEFAULT_EPISODES)
        _write_json(episodes_path, artifact)
        report_path = _rooted(root, args.episode_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_episode_markdown(artifact), encoding="utf-8")
        print(
            f"rows={artifact['signal_audit']['row_count']} "
            f"episodes={artifact['coverage']['episode_count']} "
            f"owners={artifact['coverage']['owner_count']}"
        )
        return 0

    cache: Mapping[str, Any]
    if args.stage in {"collect", "all"}:
        if cache_path.exists() and not args.force:
            cache = _read_json(cache_path)
            _require(cache.get("schema") == RAW_CACHE_SCHEMA, "cached raw schema mismatch")
        else:
            _require(args.binary is not None, "--binary is required for collect/all")
            cache = collect_same_origin_2x(
                root=root,
                binary=_rooted(root, args.binary),
            )
            _write_json(cache_path, cache)
        if args.stage == "collect":
            print(f"cache={cache_path} segments={len(cache['input_rows'])}")
            return 0
    else:
        _require(cache_path.exists(), f"raw cache not found: {cache_path}")
        cache = _read_json(cache_path)

    samples = (
        _read_rows(_rooted(root, args.episode_samples))
        if args.episode_samples is not None
        else None
    )
    analyzed = analyze_raw_cache(
        cache,
        episode_rows=samples,
        enter_threshold=args.episode_enter_threshold,
        exit_threshold=args.episode_exit_threshold,
        time_block_seconds=args.time_block_seconds,
        signal_field=args.signal_field,
    )
    ledger = analyzed["ledger"]
    _write_csv(_rooted(root, args.segment_ledger), ledger["segment_rows"])
    _write_csv(_rooted(root, args.task_ledger), ledger["task_rows"])
    _write_json(_rooted(root, args.summary), ledger["summary"])
    by_leg = aggregate_gap_rows(ledger["segment_rows"], ("leg",))
    by_source_time = aggregate_gap_rows(
        ledger["task_rows"], ("source", "release_time_block")
    )
    by_hotspot_time_leg = aggregate_gap_rows(
        ledger["segment_rows"], ("leg", "source", "release_time_block")
    )
    _write_csv(_rooted(root, args.by_leg), by_leg)
    _write_csv(_rooted(root, args.by_source_time), by_source_time)
    _write_csv(_rooted(root, args.by_hotspot_time_leg), by_hotspot_time_leg)
    report_path = _rooted(root, args.gap_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_gap_report(
            ledger["summary"], by_leg, by_source_time, by_hotspot_time_leg
        ),
        encoding="utf-8",
    )
    episode_status_path = _rooted(
        root, args.episodes or DEFAULT_EPISODE_STATUS
    )
    _write_json(episode_status_path, analyzed["episode_artifact"])
    print(
        f"segments={len(ledger['segment_rows'])} tasks={len(ledger['task_rows'])} "
        f"episodes={len(analyzed['episode_artifact']['episodes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
