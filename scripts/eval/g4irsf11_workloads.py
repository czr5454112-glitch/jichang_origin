"""Deterministic, explicitly-labelled workloads for the G4IRSF11 frontier.

These generators derive load from the processed original-day task stream. They
do not claim to replay the original Java generation rules or to create an
independent day.  Each mode is kept separate in result tables.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


FRONTIER_SCALES = (2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0)

# These seven protocols are deliberately reported as separate experiments.
# None is represented as a replay of the unavailable Java traffic generator.
FORMAL_WORKLOAD_MODES = (
    "synchronized_replica_worst_case",
    "empirical_interarrival_jitter",
    "peak_hour_only_scaling",
    "source_balanced_scaling",
    "ebs_storage_release_wave",
    "flight_bank_windows",
    "rolling_multiday_carryover",
)

# The two earlier diagnostic names stay accepted for reproducibility.  They are
# not silently folded into the seven-mode capacity claim.
DIAGNOSTIC_WORKLOAD_MODES = ("time_compressed", "stratified_replicas")
WORKLOAD_MODES = FORMAL_WORKLOAD_MODES + DIAGNOSTIC_WORKLOAD_MODES

WORKLOAD_MODE_SEMANTICS = {
    "synchronized_replica_worst_case": (
        "whole deterministic replicas retain identical release epochs; the fractional "
        "replica is selected by pallet-level SHA-256"
    ),
    "empirical_interarrival_jitter": (
        "deterministic replicas receive jitter whose magnitudes are sampled from the "
        "observed positive inter-arrival distribution"
    ),
    "peak_hour_only_scaling": (
        "one full base day plus deterministic extra replicas only inside the busiest "
        "observed 3600-second release bin"
    ),
    "source_balanced_scaling": (
        "deterministic replicas retain the source mix but source-specific phases spread "
        "simultaneous releases; this is temporal balancing, not count equalisation"
    ),
    "ebs_storage_release_wave": (
        "replicated storage-out releases are grouped into explicit five-minute EBS waves; "
        "other legs retain empirical epochs with bounded deterministic jitter"
    ),
    "flight_bank_windows": (
        "replicated releases are placed inside deterministic fifteen-minute flight-bank "
        "windows while preserving their bank membership"
    ),
    "rolling_multiday_carryover": (
        "replicas are placed on consecutive full-span days; the runtime is not reset at "
        "day boundaries so unfinished work carries over"
    ),
    "time_compressed": "diagnostic-only compression of the original release timeline",
    "stratified_replicas": "legacy diagnostic alias for deterministic jittered replicas",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"{path}: JSONL row must be an object")
                rows.append(row)
    return rows


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stable_fraction(*parts: Any) -> float:
    digest = hashlib.sha256(
        "|".join(str(part) for part in parts).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _identity(row: Mapping[str, Any]) -> str:
    return str(
        row.get(
            "segment_id",
            f"{row.get('task_id', '')}:{row.get('leg', '')}:{row.get('start', '')}:{row.get('goal', '')}",
        )
    )


def _bag_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("pallet_id", row.get("task_id", _identity(row))))


def _base_release(row: Mapping[str, Any]) -> float:
    return _number(row.get("pass_time", row.get("release_time")))


def _base_arrival(row: Mapping[str, Any]) -> float:
    return _number(row.get("original_entry_time", _base_release(row)))


def _source(row: Mapping[str, Any]) -> str:
    return str(row.get("source", f"node_{int(row['start'])}"))


def _request_row(
    row: Mapping[str, Any],
    *,
    internal_task_id: int,
    release_time: float,
    original_arrival_time: float,
    copy_index: int,
    mode: str,
    scale: float,
) -> dict[str, Any]:
    base_release = _base_release(row)
    base_deadline = _number(row.get("std", row.get("deadline", -1.0)), -1.0)
    deadline = release_time + max(0.0, base_deadline - base_release) if base_deadline > 0.0 else -1.0
    return {
        "segment_id": f"{_identity(row)}:g4irsf11_c{copy_index}",
        # Preserve the Java/source identity even when storage-in and
        # storage-out share it.  The C++ runtime assigns a separate ordinal
        # runtime_bag_id; changing task_id here would destroy provenance.
        "task_id": int(row.get("task_id", internal_task_id)),
        "original_task_id": int(row.get("task_id", internal_task_id)),
        "pallet_id": int(row.get("pallet_id", row.get("task_id", internal_task_id))),
        "leg": str(row.get("leg", "direct")),
        "release_time": release_time,
        "pass_time": release_time,
        "original_arrival_time": original_arrival_time,
        "g4irsf7_original_pass_time": original_arrival_time,
        "deadline": deadline,
        "start": int(row["start"]),
        "goal": int(row["goal"]),
        "source": _source(row),
        "source_line": row.get("source_line", ""),
        "generation_copy_index": copy_index,
        "generation_mode": mode,
        "scale": scale,
        "future_route_stored": False,
    }


def build_workload(
    base_rows: Sequence[Mapping[str, Any]],
    *,
    scale: float,
    mode: str,
    seed: str = "czr005-g4irsf11-workload-v1",
) -> list[dict[str, Any]]:
    if not base_rows:
        raise ValueError("base workload must not be empty")
    if scale <= 0.0:
        raise ValueError("scale must be positive")
    if mode not in WORKLOAD_MODES:
        raise ValueError(f"unknown workload mode: {mode}")
    canonical = sorted(
        base_rows,
        key=lambda row: (_base_release(row), _identity(row), int(row.get("task_id", 0))),
    )
    minimum_release = min(_base_release(row) for row in canonical)
    minimum_arrival = min(_base_arrival(row) for row in canonical)
    releases = sorted({_base_release(row) for row in canonical})
    interarrivals = [right - left for left, right in zip(releases, releases[1:]) if right > left]
    median_interarrival = statistics.median(interarrivals) if interarrivals else 1.0

    generated: list[dict[str, Any]] = []

    def append_request(
        row: Mapping[str, Any],
        *,
        release: float,
        arrival: float,
        copy_index: int,
    ) -> None:
        generated.append(
            _request_row(
                row,
                internal_task_id=-1,
                release_time=release,
                original_arrival_time=arrival,
                copy_index=copy_index,
                mode=mode,
                scale=scale,
            )
        )

    def included(row: Mapping[str, Any], copy_index: int, whole: int, fractional: float) -> bool:
        return copy_index < whole or (
            copy_index == whole
            and fractional > 0.0
            and _stable_fraction(seed, mode, _bag_identity(row), "include") < fractional
        )

    if mode == "time_compressed":
        for row in canonical:
            release = minimum_release + (_base_release(row) - minimum_release) / scale
            arrival = minimum_arrival + (_base_arrival(row) - minimum_arrival) / scale
            append_request(row, release=release, arrival=arrival, copy_index=0)
    elif mode == "peak_hour_only_scaling":
        # Select the peak from the observed release stream before adding any
        # traffic.  A pallet is eligible when any one of its legs is in the
        # peak bin, so a derived copy never contains only half a multi-leg bag.
        bins: dict[int, int] = {}
        for row in canonical:
            hour = int((_base_release(row) - minimum_release) // 3600.0)
            bins[hour] = bins.get(hour, 0) + 1
        peak_hour = min(bins, key=lambda value: (-bins[value], value))
        eligible_bags = {
            _bag_identity(row)
            for row in canonical
            if int((_base_release(row) - minimum_release) // 3600.0) == peak_hour
        }
        for row in canonical:
            append_request(
                row,
                release=_base_release(row),
                arrival=_base_arrival(row),
                copy_index=0,
            )
        extra = scale - 1.0
        whole_extra = int(math.floor(extra))
        fractional_extra = extra - whole_extra
        replica_count = whole_extra + (1 if fractional_extra > 0.0 else 0)
        for extra_index in range(replica_count):
            copy_index = extra_index + 1
            for row in canonical:
                if _bag_identity(row) not in eligible_bags:
                    continue
                if not included(row, extra_index, whole_extra, fractional_extra):
                    continue
                empirical = interarrivals[
                    min(
                        len(interarrivals) - 1,
                        int(_stable_fraction(seed, _identity(row), copy_index, "peak-gap") * len(interarrivals)),
                    )
                ] if interarrivals else median_interarrival
                jitter = _stable_fraction(seed, _identity(row), copy_index, "peak-jitter") * empirical
                append_request(
                    row,
                    release=_base_release(row) + jitter,
                    arrival=_base_arrival(row) + jitter,
                    copy_index=copy_index,
                )
    else:
        whole = int(math.floor(scale))
        fractional = scale - whole
        replica_count = whole + (1 if fractional > 0.0 else 0)
        sources = sorted({_source(row) for row in canonical})
        source_rank = {source: index for index, source in enumerate(sources)}
        day_span = max(_base_release(row) for row in canonical) - minimum_release
        day_stride = max(86_400.0, day_span + median_interarrival)
        for copy_index in range(replica_count):
            for row in canonical:
                identity = _identity(row)
                if not included(row, copy_index, whole, fractional):
                    continue

                release = _base_release(row)
                arrival = _base_arrival(row)
                if mode == "synchronized_replica_worst_case":
                    shift = 0.0
                elif mode in {"empirical_interarrival_jitter", "stratified_replicas"}:
                    empirical = interarrivals[
                        min(
                            len(interarrivals) - 1,
                            int(_stable_fraction(seed, identity, copy_index, "gap") * len(interarrivals)),
                        )
                    ] if interarrivals else median_interarrival
                    shift = _stable_fraction(seed, identity, copy_index, "jitter") * empirical
                elif mode == "source_balanced_scaling":
                    # Spread source phases over one empirical inter-arrival.
                    # Counts are intentionally not altered or called balanced.
                    phase_slots = max(1, len(sources) * replica_count)
                    slot = source_rank[_source(row)] * replica_count + copy_index
                    shift = median_interarrival * slot / phase_slots
                elif mode == "ebs_storage_release_wave":
                    if str(row.get("leg", "")) == "storage_out":
                        wave_start = minimum_release + math.floor(
                            (release - minimum_release) / 300.0
                        ) * 300.0
                        release = wave_start + copy_index * 1.0e-3
                        arrival += release - _base_release(row)
                        shift = 0.0
                    else:
                        shift = _stable_fraction(seed, identity, copy_index, "ebs-jitter") * min(
                            median_interarrival, 30.0
                        )
                elif mode == "flight_bank_windows":
                    bank_start = minimum_release + math.floor(
                        (release - minimum_release) / 900.0
                    ) * 900.0
                    bank_offset = 120.0 * _stable_fraction(seed, identity, copy_index, "bank")
                    transformed = bank_start + bank_offset
                    arrival += transformed - release
                    release = transformed
                    shift = 0.0
                elif mode == "rolling_multiday_carryover":
                    shift = copy_index * day_stride
                else:  # pragma: no cover - guarded by WORKLOAD_MODES above
                    raise AssertionError(mode)
                append_request(
                    row,
                    release=release + shift,
                    arrival=arrival + shift,
                    copy_index=copy_index,
                )

    generated.sort(key=lambda row: (row["release_time"], row["segment_id"]))
    segment_ids = [str(row["segment_id"]) for row in generated]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError("generated segment_id values must be unique")
    return generated


def binding_bag_records(rows: Iterable[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    records: list[tuple[Any, ...]] = []
    seen_segments: set[str] = set()
    for row in rows:
        task_id = int(row["task_id"])
        segment_id = str(row["segment_id"])
        if segment_id in seen_segments:
            raise ValueError(f"event-runtime segment_id must be unique: {segment_id}")
        seen_segments.add(segment_id)
        records.append(
            (
                segment_id,
                task_id,
                float(row["release_time"]),
                float(row["deadline"]),
                int(row["start"]),
                int(row["goal"]),
                str(row["source"]),
            )
        )
    return records


def namespace_workload(
    rows: Sequence[Mapping[str, Any]], *, scenario: str, task_id_offset: int = 0
) -> list[dict[str, Any]]:
    if task_id_offset != 0:
        raise ValueError(
            "task_id_offset would rewrite original source identity; use scenario/segment_id namespace instead"
        )
    if not scenario:
        raise ValueError("scenario must be non-empty")
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["segment_id"] = f"{row['segment_id']}:{scenario}"
        item["scenario"] = scenario
        result.append(item)
    return result


def workload_manifest(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot describe an empty workload")
    releases = [float(row["release_time"]) for row in rows]
    sources = {str(row["source"]) for row in rows}
    od_pairs = {(int(row["start"]), int(row["goal"])) for row in rows}
    return {
        "generation_mode": rows[0]["generation_mode"],
        "generation_semantics": WORKLOAD_MODE_SEMANTICS[str(rows[0]["generation_mode"])],
        "scale": rows[0]["scale"],
        "task_segment_count": len(rows),
        "source_count": len(sources),
        "od_count": len(od_pairs),
        "min_release_time": min(releases),
        "max_release_time": max(releases),
        "arrival_span_seconds": max(releases) - min(releases),
        "independent_day_generation": False,
        "original_java_rule_replay": False,
        "stores_future_route": False,
    }


def aggregate_raw_bags(
    workload_rows: Sequence[Mapping[str, Any]],
    segment_results: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Join runtime segments and aggregate the original multi-leg bags.

    Original-entry elapsed time and Java-release segment THT stay separate.
    The latter is the sum of admitted-to-finish time for each completed leg,
    excluding scheduled storage dwell between legs.
    """

    workload_by_segment = {str(row["segment_id"]): row for row in workload_rows}
    if len(workload_by_segment) != len(workload_rows):
        raise ValueError("workload segment_id values must be unique")
    runtime_by_segment = {str(row["segment_id"]): row for row in segment_results}
    if len(runtime_by_segment) != len(segment_results):
        raise ValueError("runtime segment_id values must be unique")
    unknown = sorted(set(runtime_by_segment) - set(workload_by_segment))
    if unknown:
        raise ValueError(f"runtime returned unknown segment_id values: {unknown[:10]}")
    missing = sorted(set(workload_by_segment) - set(runtime_by_segment))
    if missing:
        raise ValueError(f"runtime omitted segment_id values: {missing[:10]}")

    enriched: list[dict[str, Any]] = []
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for segment_id, workload in workload_by_segment.items():
        runtime = runtime_by_segment.get(segment_id, {})
        row = dict(runtime)
        row.update(
            {
                "task_id": int(workload["task_id"]),
                "segment_id": segment_id,
                "original_task_id": workload["original_task_id"],
                "pallet_id": workload["pallet_id"],
                "generation_copy_index": workload["generation_copy_index"],
                "leg": workload["leg"],
                "original_arrival_time": workload["original_arrival_time"],
                "scheduled_release_time": workload["release_time"],
                "deadline": workload["deadline"],
                "source": workload["source"],
                "completed": bool(runtime.get("completed", runtime.get("complete", False))),
            }
        )
        enriched.append(row)
        key = (int(workload["pallet_id"]), int(workload["generation_copy_index"]))
        groups.setdefault(key, []).append(row)

    aggregated: list[dict[str, Any]] = []
    for (pallet_id, copy_index), rows in sorted(groups.items()):
        completed = all(bool(row["completed"]) for row in rows)
        finish_times = [
            float(row["finish_time"])
            for row in rows
            if row.get("finish_time") not in (None, "", -1, -1.0)
        ]
        admitted_times = [
            float(row["admitted_time"])
            for row in rows
            if row.get("admitted_time") not in (None, "", -1, -1.0)
        ]
        java_tth = sum(
            max(0.0, float(row["finish_time"]) - float(row["admitted_time"]))
            for row in rows
            if row.get("finish_time") not in (None, "", -1, -1.0)
            and row.get("admitted_time") not in (None, "", -1, -1.0)
        )
        original_arrival = min(float(row["original_arrival_time"]) for row in rows)
        finish = max(finish_times) if completed and len(finish_times) == len(rows) else -1.0
        aggregated.append(
            {
                "task_id": f"{pallet_id}:c{copy_index}",
                "pallet_id": pallet_id,
                "generation_copy_index": copy_index,
                "source": rows[0]["source"],
                "release_time": original_arrival,
                "original_arrival_time": original_arrival,
                "admitted_time": min(admitted_times) if admitted_times else -1.0,
                "finish_time": finish,
                "deadline": max(float(row["deadline"]) for row in rows),
                "total_wait": sum(float(row.get("total_local_wait", 0.0)) for row in rows),
                "java_release_tth_seconds": java_tth,
                "segment_count": len(rows),
                "completed_segment_count": sum(bool(row["completed"]) for row in rows),
                "complete": completed,
                "failure_reason": "" if completed else "one_or_more_segments_failed",
            }
        )
    return aggregated, enriched


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count
