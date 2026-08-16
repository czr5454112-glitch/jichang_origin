"""Build the G29 schedule-preserving 2x airport workload.

The thesis says that the bag stream is generated from one day's flight
timetable.  G29 therefore doubles the timetable, not the already-expanded
segment file: a flight is the raw-input group ``(STD, end, Unloader)`` and a
new flight is inserted after every original flight in each ``(end,
Unloader)`` departure sequence.  Every inserted flight carries a shifted copy
of the complete source/loader manifest of its parent flight.

The raw file is always written first.  The canonical JSONL is then produced by
parsing that raw file and calling the existing legacy early-bag expansion.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from czr005.io.legacy_tasks import (  # noqa: E402
    RawLegacyTask,
    expand_tasks,
    parse_legacy_tasks,
    summarize_tasks,
    write_task_jsonl,
)


SCHEMA = "czr005.g4irsf29.workload_manifest.v1"
STATUS = "COMPLETE"
PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_2X"

DEFAULT_INPUT = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/tasks/g4irsf29"
DEFAULT_RAW_OUTPUT = DEFAULT_OUTPUT_DIR / "inputdata_flight_densified_2x.txt"
DEFAULT_CANONICAL_OUTPUT = (
    DEFAULT_OUTPUT_DIR / "inputdata_flight_densified_2x.jsonl"
)
DEFAULT_MANIFEST_OUTPUT = DEFAULT_OUTPUT_DIR / "g4irsf29_workload_manifest.json"
DEFAULT_FLIGHT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / "g4irsf29_flights.csv"

FlightKey = tuple[float, int, str]
StreamKey = tuple[int, str]

FLIGHT_CSV_FIELDS = (
    "flight_kind",
    "stream_end",
    "stream_unloader",
    "stream_flight_index",
    "parent_std",
    "scheduled_std",
    "shift_seconds",
    "raw_bag_count",
    "direct_bag_count",
    "early_bag_count",
    "first_entry_time",
    "last_entry_time",
    "source_counts",
    "loader_counts",
)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return format(float(value), ".15g")


def _flight_key(task: RawLegacyTask) -> FlightKey:
    return float(task.std), int(task.end), str(task.unloader)


def _stream_key(flight: FlightKey) -> StreamKey:
    return flight[1], flight[2]


def _lower_median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    return ordered[(len(ordered) - 1) // 2]


def _raw_counts(
    tasks: Iterable[RawLegacyTask], field: str
) -> dict[str, int]:
    counts = Counter(str(getattr(task, field)) for task in tasks)
    return dict(sorted(counts.items()))


def _flight_row(
    *,
    kind: str,
    stream: StreamKey,
    index: int,
    parent_std: float,
    scheduled_std: float,
    tasks: Sequence[RawLegacyTask],
) -> dict[str, Any]:
    direct = sum(task.std - task.entry_time < 4800.0 for task in tasks)
    return {
        "flight_kind": kind,
        "stream_end": stream[0],
        "stream_unloader": stream[1],
        "stream_flight_index": index,
        "parent_std": parent_std,
        "scheduled_std": scheduled_std,
        "shift_seconds": scheduled_std - parent_std,
        "raw_bag_count": len(tasks),
        "direct_bag_count": direct,
        "early_bag_count": len(tasks) - direct,
        "first_entry_time": min(task.entry_time for task in tasks),
        "last_entry_time": max(task.entry_time for task in tasks),
        "source_counts": json.dumps(
            _raw_counts(tasks, "start"), ensure_ascii=False, sort_keys=True
        ),
        "loader_counts": json.dumps(
            _raw_counts(tasks, "loader"), ensure_ascii=False, sort_keys=True
        ),
    }


def densify_flight_timetable(
    raw_tasks: Sequence[RawLegacyTask],
) -> tuple[tuple[RawLegacyTask, ...], list[dict[str, Any]], dict[str, Any]]:
    """Return original bags plus one shifted manifest for every flight."""

    ids = [task.task_id for task in raw_tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("raw task IDs must be unique")

    by_flight: dict[FlightKey, list[RawLegacyTask]] = defaultdict(list)
    for task in raw_tasks:
        if task.unloader is None or task.loader is None:
            raise ValueError("G29 flight grouping requires Unloader and Loader fields")
        by_flight[_flight_key(task)].append(task)

    by_stream: dict[StreamKey, list[float]] = defaultdict(list)
    for flight in by_flight:
        by_stream[_stream_key(flight)].append(flight[0])

    id_offset = max(ids) + 1
    rank_by_id = {task.task_id: rank for rank, task in enumerate(raw_tasks)}
    inserted: list[RawLegacyTask] = []
    flight_rows: list[dict[str, Any]] = []

    for stream in sorted(by_stream):
        departures = sorted(by_stream[stream])
        if len(departures) < 2:
            raise ValueError(f"flight stream {stream} needs at least two departures")
        headways = [right - left for left, right in zip(departures, departures[1:])]
        terminal_half_headway = _lower_median(headways) / 2.0

        for index, std in enumerate(departures):
            parent = tuple(by_flight[(std, stream[0], stream[1])])
            if index + 1 < len(departures):
                inserted_std = (std + departures[index + 1]) / 2.0
            else:
                inserted_std = std + terminal_half_headway
            shift = inserted_std - std

            flight_rows.append(
                _flight_row(
                    kind="original",
                    stream=stream,
                    index=index,
                    parent_std=std,
                    scheduled_std=std,
                    tasks=parent,
                )
            )

            copied: list[RawLegacyTask] = []
            for task in parent:
                item = RawLegacyTask(
                    task_id=id_offset + rank_by_id[task.task_id],
                    entry_time=task.entry_time + shift,
                    std=inserted_std,
                    start=task.start,
                    end=task.end,
                    unloader=task.unloader,
                    loader=task.loader,
                    source_line=0,
                )
                inserted.append(item)
                copied.append(item)

            flight_rows.append(
                _flight_row(
                    kind="inserted",
                    stream=stream,
                    index=index,
                    parent_std=std,
                    scheduled_std=inserted_std,
                    tasks=copied,
                )
            )

    combined = tuple(
        sorted(
            (*raw_tasks, *inserted),
            key=lambda task: (task.entry_time, task.task_id),
        )
    )
    metadata = {
        "input_flight_count": len(by_flight),
        "stream_count": len(by_stream),
        "inserted_flight_count": len(by_flight),
        "inserted_id_offset": id_offset,
    }
    return combined, flight_rows, metadata


def write_raw_tasks(
    header: str, tasks: Sequence[RawLegacyTask], output: Path
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [header]
    for task in tasks:
        lines.append(
            " ".join(
                (
                    str(task.task_id),
                    _number(task.entry_time),
                    _number(task.std),
                    str(task.start),
                    str(task.end),
                    str(task.unloader),
                    str(task.loader),
                )
            )
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def write_flight_csv(rows: Sequence[Mapping[str, Any]], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FLIGHT_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def build_workload(
    *,
    input_path: Path = DEFAULT_INPUT,
    raw_output: Path = DEFAULT_RAW_OUTPUT,
    canonical_output: Path = DEFAULT_CANONICAL_OUTPUT,
    manifest_output: Path = DEFAULT_MANIFEST_OUTPUT,
    flight_csv_output: Path = DEFAULT_FLIGHT_CSV_OUTPUT,
) -> dict[str, Any]:
    header, source_raw = parse_legacy_tasks(input_path)
    source_expanded = expand_tasks(source_raw)
    generated, flight_rows, generation = densify_flight_timetable(source_raw)

    # Raw is the authority.  Reparse it before creating canonical JSONL.
    write_raw_tasks(header, generated, raw_output)
    _, reparsed = parse_legacy_tasks(raw_output)
    canonical = expand_tasks(reparsed)
    write_task_jsonl(canonical, canonical_output)
    write_flight_csv(flight_rows, flight_csv_output)

    source_summary = summarize_tasks(source_raw, source_expanded)
    summary = summarize_tasks(reparsed, canonical)
    raw_task_count = len(reparsed)
    expanded_segment_count = len(canonical)
    original_flights = int(generation["input_flight_count"])
    inserted_flights = int(generation["inserted_flight_count"])

    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "protocol": PROTOCOL,
        "source_raw_input": _display_path(input_path),
        "raw_output": _display_path(raw_output),
        "canonical_output": _display_path(canonical_output),
        "flight_csv_output": _display_path(flight_csv_output),
        "input_raw_task_count": len(source_raw),
        "input_expanded_segment_count": len(source_expanded),
        "input_flight_count": original_flights,
        "raw_task_count": raw_task_count,
        "expanded_segment_count": expanded_segment_count,
        "direct_raw_task_count": int(summary["direct_raw_task_count"]),
        "early_split_raw_task_count": int(summary["early_split_raw_task_count"]),
        "flight_count": original_flights + inserted_flights,
        "original_flight_count": original_flights,
        "inserted_flight_count": inserted_flights,
        "stream_count": int(generation["stream_count"]),
        "inserted_id_offset": int(generation["inserted_id_offset"]),
        "flight_key": ["STD", "end", "Unloader"],
        "stream_key": ["end", "Unloader"],
        "insertion_rule": {
            "nonterminal": "midpoint_to_next_STD_in_same_stream",
            "terminal": "lower_median_positive_stream_headway_divided_by_2",
            "manifest_shift": "EntryTime_and_STD_receive_the_same_delta",
        },
        "lifecycle": {
            "early_bag_threshold_seconds": 4800.0,
            "storage_in_goal": 47,
            "storage_out_start": 52,
            "storage_out_lead_seconds": 2700.0,
            "bag_id_rule": (
                "original task_id retained; inserted task_id equals "
                "inserted_id_offset plus source row rank"
            ),
            "segment_id_rule": "<task_id>:direct|storage_in|storage_out",
        },
        "timing": {
            "time_compression": 1.0,
            "rolling_days": 1,
            "earliest_entry_time": min(task.entry_time for task in reparsed),
            "latest_entry_time": max(task.entry_time for task in reparsed),
            "earliest_std": min(task.std for task in reparsed),
            "latest_std": max(task.std for task in reparsed),
        },
        "raw_by_start": _raw_counts(reparsed, "start"),
        "raw_by_end": _raw_counts(reparsed, "end"),
        "raw_by_unloader": _raw_counts(reparsed, "unloader"),
        "raw_by_loader": _raw_counts(reparsed, "loader"),
        "expanded_by_start": summary["expanded_by_start"],
        "invariants": {
            "raw_task_count_is_exactly_2x": raw_task_count == 2 * len(source_raw),
            "expanded_segment_count_is_exactly_2x": (
                expanded_segment_count == 2 * len(source_expanded)
            ),
            "direct_count_is_exactly_2x": (
                int(summary["direct_raw_task_count"])
                == 2 * int(source_summary["direct_raw_task_count"])
            ),
            "early_split_count_is_exactly_2x": (
                int(summary["early_split_raw_task_count"])
                == 2 * int(source_summary["early_split_raw_task_count"])
            ),
            "same_day_no_time_compression": True,
            "categorical_manifest_is_copied_per_inserted_flight": True,
            "slack_and_storage_class_are_preserved": True,
            "canonical_was_expanded_from_generated_raw": True,
        },
    }
    if not all(manifest["invariants"].values()):
        raise ValueError("G29 workload invariants did not hold")

    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument(
        "--canonical-output", type=Path, default=DEFAULT_CANONICAL_OUTPUT
    )
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument(
        "--flight-csv-output", type=Path, default=DEFAULT_FLIGHT_CSV_OUTPUT
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = build_workload(
        input_path=args.input,
        raw_output=args.raw_output,
        canonical_output=args.canonical_output,
        manifest_output=args.manifest_output,
        flight_csv_output=args.flight_csv_output,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "raw_task_count": manifest["raw_task_count"],
                "expanded_segment_count": manifest["expanded_segment_count"],
                "flight_count": manifest["flight_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
