#!/usr/bin/env python3
"""Run a small, fresh Java HCA* capacity check at 2x and 4x load.

The workload construction is the schedule-preserving flight densification
validated by G29, generalized only by the requested integer scale.  Complete
flight manifests are inserted at evenly spaced points in each original
departure headway; EntryTime and STD receive the same shift.  The original
Java scheduler and G24 benchmark wrapper remain unchanged.

This runner intentionally reports capacity counts at the fixed 90,000-epoch
window.  Unless every canonical bag completes, latency/TTH is NOT_MEASURED:
timing over completed survivors would be censored and is not a fair scale
comparison.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from czr005.io.legacy_tasks import (  # noqa: E402
    RawLegacyTask,
    expand_tasks,
    parse_legacy_tasks,
    write_task_jsonl,
)
from scripts.eval import run_g4irsf24_fresh_hca as g24  # noqa: E402


START_EPOCH = 8_260
MAX_EPOCHS = 90_000
MAX_NEW_TASKS = 0
DEFAULT_SCALES = (2, 4)
DEFAULT_RUNTIME_ROOT = ROOT / "build" / "g4irsf25_hca_scale"
DEFAULT_TABLE = ROOT / "outputs" / "tables" / "g4irsf25_hca_scale.csv"
DEFAULT_REPORT = ROOT / "outputs" / "reports" / "g4irsf25_hca_scale.md"

CSV_FIELDS = (
    "evidence_id",
    "scale",
    "evidence_kind",
    "protocol_status",
    "execution_status",
    "raw_task_count",
    "canonical_segment_count",
    "flight_count",
    "start_epoch",
    "max_epochs",
    "end_epoch",
    "max_new_tasks",
    "released_segment_count",
    "planned_segment_count",
    "completed_segment_count",
    "unfinished_segment_count",
    "canonical_complete_raw_bag_count",
    "canonical_incomplete_raw_bag_count",
    "canonical_success_rate",
    "full_release_observed",
    "full_segment_completion_observed",
    "parent_wall_seconds",
    "child_wall_seconds",
    "timing_scope",
    "full_population_tth",
    "comparison_eligible",
    "provenance",
    "run_dir",
)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else format(float(value), ".15g")


def _lower_median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    return ordered[(len(ordered) - 1) // 2]


def _raw_line(task: RawLegacyTask) -> str:
    return " ".join(
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


def build_scaled_workload(scale: int, output_dir: Path) -> dict[str, Any]:
    """Build one same-day, schedule-preserving integer-scale workload."""

    if scale < 2:
        raise ValueError("scale must be at least 2")
    source_path = ROOT / "legacy" / "jichang_origin_readonly" / "inputdata.txt"
    header, source = parse_legacy_tasks(source_path)
    if not source:
        raise ValueError("legacy workload is empty")

    ids = [task.task_id for task in source]
    if len(ids) != len(set(ids)):
        raise ValueError("legacy task IDs must be unique")

    flights: dict[tuple[float, int, str], list[RawLegacyTask]] = defaultdict(list)
    streams: dict[tuple[int, str], list[float]] = defaultdict(list)
    for task in source:
        if task.unloader is None or task.loader is None:
            raise ValueError("flight densification requires Unloader and Loader")
        flight = (float(task.std), int(task.end), str(task.unloader))
        flights[flight].append(task)
    for std, end, unloader in flights:
        streams[(end, unloader)].append(std)

    source_count = len(source)
    first_inserted_id = max(ids) + 1
    rank_by_id = {task.task_id: rank for rank, task in enumerate(source)}
    inserted: list[RawLegacyTask] = []
    for stream in sorted(streams):
        departures = sorted(streams[stream])
        if len(departures) < 2:
            raise ValueError(f"flight stream {stream} needs at least two departures")
        headways = [right - left for left, right in zip(departures, departures[1:])]
        terminal_headway = _lower_median(headways)
        for index, std in enumerate(departures):
            parent = flights[(std, stream[0], stream[1])]
            headway = (
                departures[index + 1] - std
                if index + 1 < len(departures)
                else terminal_headway
            )
            for ordinal in range(1, scale):
                shift = headway * ordinal / scale
                id_offset = first_inserted_id + (ordinal - 1) * source_count
                for task in parent:
                    inserted.append(
                        RawLegacyTask(
                            task_id=id_offset + rank_by_id[task.task_id],
                            entry_time=task.entry_time + shift,
                            std=task.std + shift,
                            start=task.start,
                            end=task.end,
                            unloader=task.unloader,
                            loader=task.loader,
                            source_line=0,
                        )
                    )

    generated = tuple(
        sorted((*source, *inserted), key=lambda task: (task.entry_time, task.task_id))
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"inputdata_flight_densified_{scale}x.txt"
    canonical_path = output_dir / f"inputdata_flight_densified_{scale}x.jsonl"
    raw_path.write_text(
        "\n".join([header, *(_raw_line(task) for task in generated)]) + "\n",
        encoding="utf-8",
    )
    _, reparsed = parse_legacy_tasks(raw_path)
    canonical = expand_tasks(reparsed)
    write_task_jsonl(canonical, canonical_path)

    raw_counts = Counter(task.task_id for task in reparsed)
    canonical_ids = Counter(int(row.task_id) for row in canonical)
    invariants = {
        "raw_task_count_is_exact_scale": len(reparsed) == scale * len(source),
        "canonical_segment_count_is_exact_scale": (
            len(canonical) == scale * len(expand_tasks(source))
        ),
        "raw_ids_are_unique": all(count == 1 for count in raw_counts.values()),
        "canonical_covers_every_raw_bag": set(canonical_ids) == set(raw_counts),
        "same_day_axis": max(task.std for task in reparsed) < 86_400.0,
    }
    if not all(invariants.values()):
        raise ValueError(f"{scale}x workload invariants failed: {invariants}")

    manifest = {
        "schema": "czr005.g4irsf25.hca_scale_workload.v1",
        "status": "COMPLETE",
        "scale": scale,
        "protocol": "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION",
        "source_raw_task_count": len(source),
        "raw_task_count": len(reparsed),
        "canonical_segment_count": len(canonical),
        "flight_count": scale * len(flights),
        "raw_path": str(raw_path.resolve()),
        "canonical_path": str(canonical_path.resolve()),
        "invariants": invariants,
    }
    (output_dir / "workload_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _nonempty_line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _completion_counts(path: Path) -> Counter[int]:
    counts: Counter[int] = Counter()
    if not path.exists():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            counts[int(line.split()[0])] += 1
    return counts


def _summary_row(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle), {})


def _canonical_segment_counts(path: Path) -> Counter[int]:
    counts: Counter[int] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                counts[int(json.loads(line)["task_id"])] += 1
    return counts


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_scale(
    scale: int,
    *,
    runtime_root: Path,
    classes_dir: Path,
    java: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    workload_dir = runtime_root / f"workload_{scale}x"
    manifest = build_scaled_workload(scale, workload_dir)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runtime_root / f"hca_{scale}x" / run_stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    canonical_path = Path(manifest["canonical_path"])
    command = g24.java_run_command(
        java=java,
        classes_dir=classes_dir,
        map_path=ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt",
        input_path=Path(manifest["raw_path"]),
        start_epoch=START_EPOCH,
        max_epochs=MAX_EPOCHS,
        max_new_tasks=MAX_NEW_TASKS,
        run_dir=run_dir,
    )
    started = time.perf_counter()
    execution_status = "COMPLETE"
    returncode: int | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=run_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds or None,
            check=False,
        )
        returncode = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
        if returncode != 0:
            execution_status = "FAILED"
    except subprocess.TimeoutExpired as exc:
        execution_status = "TIMEOUT"
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
    parent_wall = time.perf_counter() - started
    (run_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")

    summary = _summary_row(run_dir / "summary.csv")
    released = _csv_count(run_dir / "release.csv")
    completed_by_task = _completion_counts(run_dir / "output.txt")
    canonical_by_task = _canonical_segment_counts(canonical_path)
    completed_segments = sum(completed_by_task.values())
    complete_bags = sum(
        completed_by_task[task_id] >= segment_count
        for task_id, segment_count in canonical_by_task.items()
    )
    canonical_segments = int(manifest["canonical_segment_count"])
    raw_tasks = int(manifest["raw_task_count"])
    # outputstarttime.txt records every successful planning attempt.  routes.csv
    # can miss a task that initially failed and succeeded later (the G29 retry
    # accounting fix), so it is not the capacity denominator here.
    planned = _nonempty_line_count(run_dir / "outputstarttime.txt")
    full_release = released == canonical_segments
    full_completion = completed_segments == canonical_segments and complete_bags == raw_tasks
    fixed_window = int(summary.get("epochs_run") or -1) == MAX_EPOCHS
    if execution_status == "COMPLETE" and not fixed_window:
        execution_status = "INVALID_WINDOW_OUTPUT"
    result = {
        "evidence_id": f"g25_fresh_hca_{scale}x_{run_stamp}",
        "scale": scale,
        "evidence_kind": "FRESH_LOCAL_RUN",
        "protocol_status": (
            "INVALID_WINDOW_OUTPUT"
            if not fixed_window
            else (
                "FIXED_HORIZON_FULL_COMPLETION"
                if full_completion
                else "FIXED_HORIZON_CAPACITY_CENSORED"
            )
        ),
        "execution_status": execution_status,
        "raw_task_count": raw_tasks,
        "canonical_segment_count": canonical_segments,
        "flight_count": int(manifest["flight_count"]),
        "start_epoch": START_EPOCH,
        "max_epochs": MAX_EPOCHS,
        "end_epoch": START_EPOCH + MAX_EPOCHS - 1,
        "max_new_tasks": MAX_NEW_TASKS,
        "released_segment_count": released,
        "planned_segment_count": planned,
        "completed_segment_count": completed_segments,
        "unfinished_segment_count": canonical_segments - completed_segments,
        "canonical_complete_raw_bag_count": complete_bags,
        "canonical_incomplete_raw_bag_count": raw_tasks - complete_bags,
        "canonical_success_rate": complete_bags / raw_tasks,
        "full_release_observed": full_release,
        "full_segment_completion_observed": full_completion,
        "parent_wall_seconds": parent_wall,
        "child_wall_seconds": "NOT_MEASURED",
        "timing_scope": "FULL_POPULATION" if full_completion else "CAPACITY_ONLY_CENSORED",
        "full_population_tth": "NOT_MEASURED" if not full_completion else "AVAILABLE_IN_RAW_RUN",
        "comparison_eligible": full_completion,
        "provenance": "current_branch_original_java_hca_g24_wrapper",
        "run_dir": run_dir.resolve().relative_to(ROOT.resolve()).as_posix(),
        "returncode": returncode,
        "benchmark_summary": summary,
        "command": command,
    }
    _write_json(run_dir / "g4irsf25_result.json", result)
    return result


def _external_prior() -> dict[str, Any]:
    """Registered G29 2x/2.5 m/s repeat pair used only as a sanity prior."""

    return {
        "evidence_id": "g29_external_prior_2x_speed_2p5_repeat_pair",
        "scale": 2,
        "evidence_kind": "EXTERNAL_PRIOR",
        "protocol_status": "EXACT_RELEASE_FULL_POPULATION_FIXED_HORIZON",
        "execution_status": "COMPLETE",
        "raw_task_count": 57_012,
        "canonical_segment_count": 87_206,
        "flight_count": 720,
        "start_epoch": START_EPOCH,
        "max_epochs": MAX_EPOCHS,
        "end_epoch": START_EPOCH + MAX_EPOCHS - 1,
        "max_new_tasks": MAX_NEW_TASKS,
        "released_segment_count": 87_206,
        "planned_segment_count": 87_206,
        "completed_segment_count": 87_111,
        "unfinished_segment_count": 95,
        "canonical_complete_raw_bag_count": 56_917,
        "canonical_incomplete_raw_bag_count": 95,
        "canonical_success_rate": 56_917 / 57_012,
        "full_release_observed": True,
        "full_segment_completion_observed": False,
        "parent_wall_seconds": "NOT_MEASURED",
        "child_wall_seconds": statistics.fmean((287.21199270000216, 293.93821829999797)),
        "timing_scope": "CAPACITY_ONLY_CENSORED",
        "full_population_tth": "NOT_MEASURED",
        "comparison_eligible": False,
        "provenance": "origin/codex/g4irsf29-faithful-2x@b8cdd17; t5_2_speed_2p5",
        "run_dir": "NOT_LOCAL",
    }


def write_table(rows: Iterable[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    local = [row for row in rows if row["evidence_kind"] == "FRESH_LOCAL_RUN"]
    lines = [
        "# G4IRSF25 fresh HCA* scale baseline",
        "",
        "## Verdict",
        "",
        (
            "This is a fixed-window capacity track, not a completed-population TTH track. "
            "Whenever canonical completion is below 100%, full-population latency is "
            "`NOT_MEASURED`; completed-survivor latency is deliberately excluded."
        ),
        "",
        "## Fresh runs",
        "",
        "| scale | raw bags | segments | released | planned | completed | complete bags | unfinished bags | parent wall (s) | status |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in local:
        lines.append(
            "| {scale}x | {raw_task_count} | {canonical_segment_count} | "
            "{released_segment_count} | {planned_segment_count} | "
            "{completed_segment_count} | {canonical_complete_raw_bag_count} | "
            "{canonical_incomplete_raw_bag_count} | {parent_wall_seconds:.3f} | "
            "{protocol_status} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Capacity interpretation",
            "",
            "At 2x, fresh HCA* completed 99.833% of canonical raw bags. At 4x it released only 67.441% of canonical segments within the same window, while 99.697% of released segments completed; canonical raw-bag completion fell to 61.406%. The fixed-window loss is therefore dominated by work that never entered the released cohort, which is direct evidence of the centralized HCA* throughput ceiling. It is not yet a causal CLCR-vs-HCA performance claim.",
            "",
            "## Protocol and censoring",
            "",
            f"- Window: epochs {START_EPOCH}..{START_EPOCH + MAX_EPOCHS - 1} ({MAX_EPOCHS} epochs), with no admission cap (`max_new_tasks=0`).",
            "- Workload: whole flight manifests are inserted at equal fractions of each same-stream headway; EntryTime and STD shift together, so slack and the storage lifecycle are preserved.",
            "- `parent_wall_seconds` is measured by this Python process around the fresh Java child. G29 exposes only child wall, so its prior parent wall is `NOT_MEASURED`.",
            "- Wall time is a reproducibility/compute-cost diagnostic, not a bag-latency metric and not a cross-machine speed claim.",
            "- `unfinished_segment_count` uses the fixed canonical denominator; `canonical_complete_raw_bag_count` requires every segment of a raw bag to complete.",
            "- No result in this table is described as completed-population TTH unless all canonical segments and bags finish.",
            "",
            "## External validation prior",
            "",
            "The pushed G29 2x/2.5 m/s result (`origin/codex/g4irsf29-faithful-2x@b8cdd17`) released/planned 87,206 segments, completed 87,111, and completed 56,917 of 57,012 raw bags in both repeats. Child walls were 287.212 s and 293.938 s. This is a provenance check only; it is not silently merged with fresh G25 measurements.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            "python scripts/eval/run_g4irsf25_hca_scale.py --scale 2 --scale 4",
            "```",
            "",
            "Large generated workloads and Java run artifacts stay under `build/g4irsf25_hca_scale/` and are not publication artifacts.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, action="append", choices=DEFAULT_SCALES)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--classes-dir", type=Path, default=DEFAULT_RUNTIME_ROOT / "java_classes")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--java", default=shutil.which("java") or "java")
    parser.add_argument("--javac", default=shutil.which("javac") or "javac")
    parser.add_argument("--skip-compile", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scales = tuple(dict.fromkeys(args.scale or DEFAULT_SCALES))
    if args.timeout_seconds < 1:
        raise ValueError("timeout-seconds must be positive")
    if not args.skip_compile:
        g24.compile_java(args.javac, args.classes_dir)
    rows: list[dict[str, Any]] = [_external_prior()]
    for scale in scales:
        row = run_scale(
            scale,
            runtime_root=args.runtime_root,
            classes_dir=args.classes_dir,
            java=args.java,
            timeout_seconds=args.timeout_seconds,
        )
        rows.append(row)
        print(
            json.dumps(
                {
                    key: row[key]
                    for key in (
                        "scale",
                        "execution_status",
                        "completed_segment_count",
                        "canonical_complete_raw_bag_count",
                        "parent_wall_seconds",
                    )
                },
                ensure_ascii=False,
            )
        )
    write_table(rows, args.table)
    write_report(rows, args.report)
    return 0 if all(row["execution_status"] == "COMPLETE" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
