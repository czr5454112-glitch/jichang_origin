"""Build the G30 schedule-preserving 3x airport workload.

G30 extends the validated G29 flight-manifest protocol without duplicating
already-expanded route segments.  A flight is the raw-input group
``(STD, end, Unloader)``.  Within each ``(end, Unloader)`` departure stream,
two complete copied manifests are placed at one-third and two-thirds of every
original headway.  After the terminal flight, the same fractions of the
stream's lower-median historical headway are used.

Each copied bag receives the same delta on ``EntryTime`` and ``STD``.  This
preserves slack, direct/EBS classification, OD fields, source, loader, and the
two-leg storage lifecycle.  Raw text remains authoritative: canonical JSONL
is produced only by reparsing the generated raw file and applying the existing
legacy expansion.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005.io.legacy_tasks import (  # noqa: E402
    RawLegacyTask,
    expand_tasks,
    parse_legacy_tasks,
    summarize_tasks,
    write_task_jsonl,
)
from scripts.eval import run_g4irsf29_workload as g29  # noqa: E402


SCHEMA = "czr005.g4irsf30.workload_manifest.v1"
STATUS = "COMPLETE"
PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_3X"
SCALE = 3
INSERTED_FLIGHTS_PER_ORIGINAL = 2
DAY_AXIS_SECONDS = 86_400.0

DEFAULT_INPUT = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/tasks/g4irsf30"
DEFAULT_RAW_OUTPUT = DEFAULT_OUTPUT_DIR / "inputdata_flight_densified_3x.txt"
DEFAULT_CANONICAL_OUTPUT = (
    DEFAULT_OUTPUT_DIR / "inputdata_flight_densified_3x.jsonl"
)
DEFAULT_MANIFEST_OUTPUT = DEFAULT_OUTPUT_DIR / "g4irsf30_workload_manifest.json"
DEFAULT_FLIGHT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / "g4irsf30_flights.csv"

FlightKey = tuple[float, int, str]
StreamKey = tuple[int, str]


def _scaled_counts(
    source: Sequence[RawLegacyTask],
    generated: Sequence[RawLegacyTask],
    field: str,
) -> bool:
    source_counts = g29._raw_counts(source, field)
    expected = {key: SCALE * value for key, value in source_counts.items()}
    return g29._raw_counts(generated, field) == expected


def _copy_invariants(
    source: Sequence[RawLegacyTask],
    generated: Sequence[RawLegacyTask],
    inserted_id_offsets: Sequence[int],
) -> bool:
    by_id = {task.task_id: task for task in generated}
    if len(by_id) != len(generated):
        return False
    for offset in inserted_id_offsets:
        for rank, original in enumerate(source):
            copied = by_id.get(offset + rank)
            if copied is None:
                return False
            if (
                copied.start != original.start
                or copied.end != original.end
                or copied.unloader != original.unloader
                or copied.loader != original.loader
            ):
                return False
            original_slack = original.std - original.entry_time
            copied_slack = copied.std - copied.entry_time
            if not math.isclose(
                copied_slack, original_slack, rel_tol=0.0, abs_tol=1.0e-9
            ):
                return False
            if (copied_slack < 4_800.0) != (original_slack < 4_800.0):
                return False
    return True


def densify_flight_timetable(
    raw_tasks: Sequence[RawLegacyTask],
) -> tuple[tuple[RawLegacyTask, ...], list[dict[str, Any]], dict[str, Any]]:
    """Return the original bags plus two shifted manifests per flight."""

    if not raw_tasks:
        raise ValueError("G30 requires at least one raw task")
    ids = [task.task_id for task in raw_tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("raw task IDs must be unique")

    by_flight: dict[FlightKey, list[RawLegacyTask]] = {}
    for task in raw_tasks:
        if task.unloader is None or task.loader is None:
            raise ValueError("G30 flight grouping requires Unloader and Loader fields")
        key = (float(task.std), int(task.end), str(task.unloader))
        by_flight.setdefault(key, []).append(task)

    by_stream: dict[StreamKey, list[float]] = {}
    for std, end, unloader in by_flight:
        by_stream.setdefault((end, unloader), []).append(std)

    raw_count = len(raw_tasks)
    first_inserted_id = max(ids) + 1
    inserted_id_offsets = tuple(
        first_inserted_id + cohort * raw_count
        for cohort in range(INSERTED_FLIGHTS_PER_ORIGINAL)
    )
    rank_by_id = {task.task_id: rank for rank, task in enumerate(raw_tasks)}
    inserted: list[RawLegacyTask] = []
    flight_rows: list[dict[str, Any]] = []

    for stream in sorted(by_stream):
        departures = sorted(by_stream[stream])
        if len(departures) < 2:
            raise ValueError(f"flight stream {stream} needs at least two departures")
        headways = [right - left for left, right in zip(departures, departures[1:])]
        terminal_headway = g29._lower_median(headways)

        for index, std in enumerate(departures):
            parent = tuple(by_flight[(std, stream[0], stream[1])])
            headway = (
                departures[index + 1] - std
                if index + 1 < len(departures)
                else terminal_headway
            )
            flight_rows.append(
                g29._flight_row(
                    kind="original",
                    stream=stream,
                    index=index,
                    parent_std=std,
                    scheduled_std=std,
                    tasks=parent,
                )
            )

            for insertion_ordinal in (1, 2):
                shift = headway * insertion_ordinal / SCALE
                inserted_std = std + shift
                copied: list[RawLegacyTask] = []
                id_offset = inserted_id_offsets[insertion_ordinal - 1]
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
                    g29._flight_row(
                        kind=f"inserted_{insertion_ordinal}_of_2",
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
        "inserted_flight_count": INSERTED_FLIGHTS_PER_ORIGINAL * len(by_flight),
        "inserted_flights_per_original": INSERTED_FLIGHTS_PER_ORIGINAL,
        "inserted_id_offsets": list(inserted_id_offsets),
        "copy_invariants_pass": _copy_invariants(
            raw_tasks, combined, inserted_id_offsets
        ),
    }
    return combined, flight_rows, metadata


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

    # Preserve the G29 authority boundary: canonical always comes from raw.
    g29.write_raw_tasks(header, generated, raw_output)
    _, reparsed = parse_legacy_tasks(raw_output)
    canonical = expand_tasks(reparsed)
    write_task_jsonl(canonical, canonical_output)
    g29.write_flight_csv(flight_rows, flight_csv_output)

    source_summary = summarize_tasks(source_raw, source_expanded)
    summary = summarize_tasks(reparsed, canonical)
    raw_task_count = len(reparsed)
    expanded_segment_count = len(canonical)
    original_flights = int(generation["input_flight_count"])
    inserted_flights = int(generation["inserted_flight_count"])
    timing = {
        "time_compression": 1.0,
        "rolling_days": 1,
        "day_axis_seconds": DAY_AXIS_SECONDS,
        "earliest_entry_time": min(task.entry_time for task in reparsed),
        "latest_entry_time": max(task.entry_time for task in reparsed),
        "earliest_std": min(task.std for task in reparsed),
        "latest_std": max(task.std for task in reparsed),
    }
    same_day = (
        0.0 <= timing["earliest_entry_time"] < DAY_AXIS_SECONDS
        and 0.0 <= timing["latest_entry_time"] < DAY_AXIS_SECONDS
        and 0.0 <= timing["earliest_std"] < DAY_AXIS_SECONDS
        and 0.0 <= timing["latest_std"] < DAY_AXIS_SECONDS
    )

    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "protocol": PROTOCOL,
        "scale": SCALE,
        "source_raw_input": g29._display_path(input_path),
        "raw_output": g29._display_path(raw_output),
        "canonical_output": g29._display_path(canonical_output),
        "flight_csv_output": g29._display_path(flight_csv_output),
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
        "inserted_flights_per_original": int(
            generation["inserted_flights_per_original"]
        ),
        "stream_count": int(generation["stream_count"]),
        "inserted_id_offsets": list(generation["inserted_id_offsets"]),
        "flight_key": ["STD", "end", "Unloader"],
        "stream_key": ["end", "Unloader"],
        "insertion_rule": {
            "nonterminal": (
                "one_third_and_two_thirds_to_next_STD_in_same_stream"
            ),
            "terminal": (
                "lower_median_positive_stream_headway_times_one_third_"
                "and_two_thirds"
            ),
            "manifest_shift": "EntryTime_and_STD_receive_the_same_delta",
        },
        "lifecycle": {
            "early_bag_threshold_seconds": 4_800.0,
            "storage_in_goal": 47,
            "storage_out_start": 52,
            "storage_out_lead_seconds": 2_700.0,
            "bag_id_rule": (
                "original task_id retained; inserted cohort 1/2 uses its "
                "registered ID offset plus source row rank"
            ),
            "segment_id_rule": "<task_id>:direct|storage_in|storage_out",
        },
        "timing": timing,
        "raw_by_start": g29._raw_counts(reparsed, "start"),
        "raw_by_end": g29._raw_counts(reparsed, "end"),
        "raw_by_unloader": g29._raw_counts(reparsed, "unloader"),
        "raw_by_loader": g29._raw_counts(reparsed, "loader"),
        "expanded_by_start": summary["expanded_by_start"],
        "invariants": {
            "raw_task_count_is_exactly_3x": (
                raw_task_count == SCALE * len(source_raw)
            ),
            "expanded_segment_count_is_exactly_3x": (
                expanded_segment_count == SCALE * len(source_expanded)
            ),
            "direct_count_is_exactly_3x": (
                int(summary["direct_raw_task_count"])
                == SCALE * int(source_summary["direct_raw_task_count"])
            ),
            "early_split_count_is_exactly_3x": (
                int(summary["early_split_raw_task_count"])
                == SCALE * int(source_summary["early_split_raw_task_count"])
            ),
            "flight_count_is_exactly_3x": (
                original_flights + inserted_flights == SCALE * original_flights
            ),
            "start_counts_are_exactly_3x": _scaled_counts(
                source_raw, reparsed, "start"
            ),
            "end_counts_are_exactly_3x": _scaled_counts(
                source_raw, reparsed, "end"
            ),
            "unloader_counts_are_exactly_3x": _scaled_counts(
                source_raw, reparsed, "unloader"
            ),
            "loader_counts_are_exactly_3x": _scaled_counts(
                source_raw, reparsed, "loader"
            ),
            "same_24h_axis_no_time_compression": same_day,
            "categorical_manifest_is_copied_per_inserted_flight": bool(
                generation["copy_invariants_pass"]
            ),
            "slack_and_storage_class_are_preserved": bool(
                generation["copy_invariants_pass"]
            ),
            "canonical_was_expanded_from_generated_raw": True,
        },
    }
    if not all(manifest["invariants"].values()):
        raise ValueError("G30 workload invariants did not hold")

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
                "latest_entry_time": manifest["timing"]["latest_entry_time"],
                "latest_std": manifest["timing"]["latest_std"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
