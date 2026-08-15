"""Run and align the original Java HCA* baseline for G4IRSF24.

The Java scheduler is executed unchanged.  The external benchmark exports the
exact release epoch, the successful planning epoch, and the legacy completion
file.  This runner joins those three events to the canonical expanded input and
reports raw-bag timings under the processed-attempt, Java-release, and raw-entry
denominators.

Each measured repeat gets its own working directory and Java process.  A
completed repeat is skipped on a later invocation, so a multi-repeat campaign
can be resumed without rerunning successful repeats.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from functools import cmp_to_key
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = ROOT / "legacy" / "jichang_origin_readonly"
DEFAULT_MAP = LEGACY_ROOT / "map2.txt"
DEFAULT_INPUT = LEGACY_ROOT / "inputdata.txt"
DEFAULT_CANONICAL = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
DEFAULT_CLASSES = ROOT / "build" / "g4irsf24_java"
DEFAULT_OUTPUT = ROOT / "outputs" / "raw" / "g4irsf24_fresh_hca"
JAVA_BENCHMARK = ROOT / "benchmarks" / "java" / "LegacyIcsNoFaultWindowBenchmark.java"

PROFILE_DEFAULTS: dict[str, dict[str, int]] = {
    # A fast planning/lifecycle diagnostic.  It is not comparison-eligible.
    "bounded": {
        "start_epoch": 8260,
        "max_epochs": 5000,
        "max_new_tasks": 64,
        "repeats": 1,
        "timeout_seconds": 1800,
    },
    # The same fixed horizon used by the existing legacy full command.
    "full": {
        "start_epoch": 8260,
        "max_epochs": 90000,
        "max_new_tasks": 0,
        "repeats": 2,
        "timeout_seconds": 0,
    },
}

LIFECYCLE_FIELDS = [
    "release_ordinal",
    "segment_id",
    "task_id",
    "leg",
    "start",
    "goal",
    "original_entry_time",
    "scheduled_pass_time",
    "release_epoch",
    "processed_attempt_epoch",
    "finish_epoch",
    "complete",
]

RAW_BAG_FIELDS = [
    "task_id",
    "canonical_segment_count",
    "released_segment_count",
    "completed_segment_count",
    "canonical_bag_covered",
    "complete",
    "raw_entry_seconds",
    "java_release_seconds",
    "processed_attempt_seconds",
    "scheduled_pre_release_seconds",
    "source_wait_seconds",
    "network_time_seconds",
]


class FreshHcaError(RuntimeError):
    """Raised when independently recorded lifecycle events cannot be aligned."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_canonical(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise FreshHcaError(f"canonical input is empty: {path}")
    return rows


def _java_task_compare(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    """Match the legacy Java comparator: ``(int)(left.pass - right.pass)``."""

    return int(float(left["pass_time"]) - float(right["pass_time"]))


def _canonical_queues(
    canonical: Sequence[Mapping[str, Any]],
) -> dict[tuple[int, int, int], deque[Mapping[str, Any]]]:
    by_start: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in canonical:
        by_start[int(row["start"])].append(row)

    queues: dict[tuple[int, int, int], deque[Mapping[str, Any]]] = defaultdict(deque)
    for rows in by_start.values():
        for row in sorted(rows, key=cmp_to_key(_java_task_compare)):
            key = (int(row["task_id"]), int(row["start"]), int(row["goal"]))
            queues[key].append(row)
    return queues


def _event_key(row: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(row["task_id"]), int(row["start"]), int(row["goal"])


def _take(
    queues: Mapping[Any, deque[Any]],
    key: Any,
    label: str,
) -> Any:
    queue = queues.get(key)
    if not queue:
        raise FreshHcaError(f"{label} has no matching canonical/released segment: {key}")
    return queue.popleft()


def _parse_completions(path: Path) -> list[dict[str, float | int]]:
    if not path.exists():
        return []
    events: list[dict[str, float | int]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            raise FreshHcaError(f"invalid output.txt line {line_no}: {line!r}")
        events.append({"task_id": int(parts[0]), "finish_epoch": float(parts[1])})
    return events


def _parse_processed_attempts(
    path: Path,
) -> list[dict[str, float | int]] | None:
    """Read actual successful planning attempts from legacy outputstarttime.txt.

    The legacy route export only notices new ``saved_routes`` keys.  A task
    that initially had no path and succeeds later can therefore be absent from
    routes.csv, while this append-only legacy file still records the real
    successful attempt.
    """

    if not path.exists():
        return None
    events: list[dict[str, float | int]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4:
            raise FreshHcaError(
                f"invalid outputstarttime.txt line {line_no}: {line!r}"
            )
        events.append(
            {
                "ordinal": len(events) + 1,
                "task_id": int(parts[0]),
                "start": int(parts[1]),
                "scheduled_pass_time": float(parts[2]),
                "processed_attempt_epoch": float(parts[3]),
            }
        )
    return events


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise FreshHcaError("cannot calculate a quantile of no values")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _describe(values: Sequence[float]) -> dict[str, Any]:
    names = ("min", "p50", "mean", "p95", "p99", "max")
    if not values:
        return {
            "count": 0,
            "seconds": {name: None for name in names},
            "minutes": {name: None for name in names},
        }
    seconds = {
        "min": min(values),
        "p50": _quantile(values, 0.50),
        "mean": statistics.fmean(values),
        "p95": _quantile(values, 0.95),
        "p99": _quantile(values, 0.99),
        "max": max(values),
    }
    return {
        "count": len(values),
        "seconds": seconds,
        "minutes": {name: value / 60.0 for name, value in seconds.items()},
    }


def _build_lifecycle(
    canonical: Sequence[Mapping[str, Any]],
    releases: Sequence[Mapping[str, str]],
    routes: Sequence[Mapping[str, str]],
    completions: Sequence[Mapping[str, float | int]],
    processed_attempts: Sequence[Mapping[str, float | int]] | None = None,
) -> list[dict[str, Any]]:
    candidates = _canonical_queues(canonical)
    lifecycle: list[dict[str, Any]] = []
    released_by_key: dict[tuple[int, int, int], deque[dict[str, Any]]] = defaultdict(deque)
    released_by_task_start: dict[tuple[int, int], deque[dict[str, Any]]] = defaultdict(deque)

    for event in sorted(releases, key=lambda row: int(row["ordinal"])):
        key = _event_key(event)
        source = _take(candidates, key, "release")
        row = {
            "release_ordinal": int(event["ordinal"]),
            "segment_id": str(source["segment_id"]),
            "task_id": int(source["task_id"]),
            "leg": str(source["leg"]),
            "start": int(source["start"]),
            "goal": int(source["goal"]),
            "original_entry_time": float(source["original_entry_time"]),
            "scheduled_pass_time": float(source["pass_time"]),
            "release_epoch": float(event["release_epoch"]),
            "processed_attempt_epoch": None,
            "finish_epoch": None,
            "complete": False,
        }
        lifecycle.append(row)
        released_by_key[key].append(row)
        released_by_task_start[(int(row["task_id"]), int(row["start"]))].append(row)

    planned_by_task: dict[int, deque[dict[str, Any]]] = defaultdict(deque)
    if processed_attempts is not None:
        for event in sorted(processed_attempts, key=lambda row: int(row["ordinal"])):
            key = int(event["task_id"]), int(event["start"])
            row = _take(
                released_by_task_start,
                key,
                "processed attempt",
            )
            row["processed_attempt_epoch"] = float(event["processed_attempt_epoch"])
            planned_by_task[int(row["task_id"])].append(row)
    else:
        for event in sorted(routes, key=lambda row: int(row["ordinal"])):
            row = _take(released_by_key, _event_key(event), "planned route")
            row["processed_attempt_epoch"] = float(event["epoch"])
            planned_by_task[int(row["task_id"])].append(row)

    for event in completions:
        task_id = int(event["task_id"])
        queue = planned_by_task.get(task_id)
        if not queue:
            raise FreshHcaError(f"completion has no matching planned segment: task_id={task_id}")
        row = queue.popleft()
        row["finish_epoch"] = float(event["finish_epoch"])
        row["complete"] = True

    return lifecycle


def _aggregate_raw_bags(
    canonical: Sequence[Mapping[str, Any]], lifecycle: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    canonical_counts: dict[int, int] = defaultdict(int)
    for row in canonical:
        canonical_counts[int(row["task_id"])] += 1

    released: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in lifecycle:
        released[int(row["task_id"])].append(row)

    raw_bags: list[dict[str, Any]] = []
    for task_id, segments in sorted(released.items()):
        completed = [row for row in segments if bool(row["complete"])]
        cohort_complete = len(completed) == len(segments)
        canonical_covered = len(segments) == canonical_counts[task_id]

        timing: dict[str, float | None] = {
            "raw_entry_seconds": None,
            "java_release_seconds": None,
            "processed_attempt_seconds": None,
            "scheduled_pre_release_seconds": None,
            "source_wait_seconds": None,
            "network_time_seconds": None,
        }
        if cohort_complete:
            timing = {
                "raw_entry_seconds": sum(
                    float(row["finish_epoch"]) - float(row["original_entry_time"])
                    for row in segments
                ),
                "java_release_seconds": sum(
                    float(row["finish_epoch"]) - float(row["release_epoch"])
                    for row in segments
                ),
                "processed_attempt_seconds": sum(
                    float(row["finish_epoch"]) - float(row["processed_attempt_epoch"])
                    for row in segments
                ),
                "scheduled_pre_release_seconds": sum(
                    float(row["release_epoch"]) - float(row["original_entry_time"])
                    for row in segments
                ),
                "source_wait_seconds": sum(
                    float(row["processed_attempt_epoch"]) - float(row["release_epoch"])
                    for row in segments
                ),
                "network_time_seconds": sum(
                    float(row["finish_epoch"]) - float(row["processed_attempt_epoch"])
                    for row in segments
                ),
            }

        raw_bags.append(
            {
                "task_id": task_id,
                "canonical_segment_count": canonical_counts[task_id],
                "released_segment_count": len(segments),
                "completed_segment_count": len(completed),
                "canonical_bag_covered": canonical_covered,
                "complete": cohort_complete,
                **timing,
            }
        )
    return raw_bags


def aggregate_run(run_dir: Path, canonical_path: Path) -> dict[str, Any]:
    canonical = _load_canonical(canonical_path)
    releases = _read_csv(run_dir / "release.csv")
    routes = _read_csv(run_dir / "routes.csv")
    processed_attempts = _parse_processed_attempts(run_dir / "outputstarttime.txt")
    completions = _parse_completions(run_dir / "output.txt")
    lifecycle = _build_lifecycle(
        canonical,
        releases,
        routes,
        completions,
        processed_attempts=processed_attempts,
    )
    raw_bags = _aggregate_raw_bags(canonical, lifecycle)

    complete_bags = [row for row in raw_bags if bool(row["complete"])]
    canonical_complete_bags = [
        row
        for row in complete_bags
        if bool(row["canonical_bag_covered"])
    ]
    completed_segment_count = sum(bool(row["complete"]) for row in lifecycle)
    canonical_task_count = len({int(row["task_id"]) for row in canonical})
    comparison_eligible = (
        len(lifecycle) == len(canonical)
        and completed_segment_count == len(canonical)
        and len(complete_bags) == canonical_task_count
        and all(bool(row["canonical_bag_covered"]) for row in complete_bags)
    )

    def values(field: str) -> list[float]:
        return [float(row[field]) for row in complete_bags if row[field] is not None]

    status = _read_json(run_dir / "run_status.json")
    benchmark_summary = _read_csv(run_dir / "summary.csv")
    metrics = {
        "schema": "g4irsf24.fresh_hca.metrics.v1",
        "run_id": run_dir.name,
        "status": status.get("status", "unknown"),
        "profile": status.get("profile"),
        "scope": "canonical_full" if comparison_eligible else "released_segment_cohort",
        "survivor_only": not comparison_eligible,
        "comparison_eligible": comparison_eligible,
        "canonical_segment_count": len(canonical),
        "canonical_raw_bag_count": canonical_task_count,
        "released_segment_count": len(lifecycle),
        "processed_attempt_source": (
            "outputstarttime.txt"
            if processed_attempts is not None
            else "routes.csv_fallback"
        ),
        "processed_attempt_event_count": (
            len(processed_attempts) if processed_attempts is not None else len(routes)
        ),
        "planned_segment_count": sum(
            row["processed_attempt_epoch"] is not None for row in lifecycle
        ),
        "completed_segment_count": completed_segment_count,
        "completion_event_count": len(completions),
        "released_raw_bag_count": len(raw_bags),
        "complete_raw_bag_count": len(complete_bags),
        "incomplete_raw_bag_count": len(raw_bags) - len(complete_bags),
        "canonical_complete_raw_bag_count": len(canonical_complete_bags),
        "canonical_incomplete_raw_bag_count": canonical_task_count - len(canonical_complete_bags),
        "canonical_success_rate": len(canonical_complete_bags) / canonical_task_count,
        "fully_covered_raw_bag_count": sum(
            bool(row["canonical_bag_covered"]) for row in raw_bags
        ),
        "wall_seconds": status.get("wall_seconds"),
        "benchmark_summary": benchmark_summary[0] if benchmark_summary else None,
        "denominators": {
            "processed_attempt": _describe(values("processed_attempt_seconds")),
            "java_release": _describe(values("java_release_seconds")),
            "raw_entry": _describe(values("raw_entry_seconds")),
        },
        "components": {
            "source_wait": _describe(values("source_wait_seconds")),
            "network_time": _describe(values("network_time_seconds")),
            "scheduled_pre_release": _describe(values("scheduled_pre_release_seconds")),
        },
    }

    _write_csv(run_dir / "segment_lifecycle.csv", LIFECYCLE_FIELDS, lifecycle)
    _write_csv(run_dir / "raw_bag_timings.csv", RAW_BAG_FIELDS, raw_bags)
    _write_json(run_dir / "metrics.json", metrics)
    return metrics


def _metric(metrics: Mapping[str, Any], denominator: str, statistic: str) -> Any:
    return metrics["denominators"][denominator]["minutes"][statistic]


def aggregate_campaign(output_root: Path, canonical_path: Path) -> dict[str, Any]:
    metrics_rows: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in output_root.glob("run_*") if path.is_dir()):
        if not (run_dir / "release.csv").exists():
            continue
        metrics = aggregate_run(run_dir, canonical_path)
        metrics_rows.append(metrics)
        row: dict[str, Any] = {
            "run_id": metrics["run_id"],
            "status": metrics["status"],
            "profile": metrics["profile"],
            "scope": metrics["scope"],
            "comparison_eligible": metrics["comparison_eligible"],
            "released_segment_count": metrics["released_segment_count"],
            "processed_attempt_source": metrics["processed_attempt_source"],
            "processed_attempt_event_count": metrics["processed_attempt_event_count"],
            "planned_segment_count": metrics["planned_segment_count"],
            "completed_segment_count": metrics["completed_segment_count"],
            "released_raw_bag_count": metrics["released_raw_bag_count"],
            "complete_raw_bag_count": metrics["complete_raw_bag_count"],
            "canonical_complete_raw_bag_count": metrics["canonical_complete_raw_bag_count"],
            "canonical_incomplete_raw_bag_count": metrics["canonical_incomplete_raw_bag_count"],
            "canonical_success_rate": metrics["canonical_success_rate"],
            "wall_seconds": metrics["wall_seconds"],
        }
        for denominator in ("processed_attempt", "java_release", "raw_entry"):
            for statistic in ("min", "p50", "mean", "p95", "p99", "max"):
                row[f"{denominator}_{statistic}_minutes"] = _metric(
                    metrics, denominator, statistic
                )
        table_rows.append(row)

    table_fields = [
        "run_id",
        "status",
        "profile",
        "scope",
        "comparison_eligible",
        "released_segment_count",
        "processed_attempt_source",
        "processed_attempt_event_count",
        "planned_segment_count",
        "completed_segment_count",
        "released_raw_bag_count",
        "complete_raw_bag_count",
        "canonical_complete_raw_bag_count",
        "canonical_incomplete_raw_bag_count",
        "canonical_success_rate",
        "wall_seconds",
        *[
            f"{denominator}_{statistic}_minutes"
            for denominator in ("processed_attempt", "java_release", "raw_entry")
            for statistic in ("min", "p50", "mean", "p95", "p99", "max")
        ],
    ]
    _write_csv(output_root / "fresh_hca_runs.csv", table_fields, table_rows)
    campaign = {
        "schema": "g4irsf24.fresh_hca.campaign.v1",
        "generated_at": _utc_now(),
        "run_count": len(metrics_rows),
        "comparison_eligible_run_count": sum(
            bool(row["comparison_eligible"]) for row in metrics_rows
        ),
        "runs": metrics_rows,
    }
    _write_json(output_root / "fresh_hca_summary.json", campaign)
    return campaign


def _java_sources() -> list[Path]:
    return [
        *sorted((LEGACY_ROOT / "src" / "App").glob("*.java")),
        LEGACY_ROOT / "src" / "ICS_GUI" / "ICS_GUI.java",
        JAVA_BENCHMARK,
    ]


def compile_command(javac: str, classes_dir: Path) -> list[str]:
    return [
        javac,
        "-encoding",
        "UTF-8",
        "-d",
        str(classes_dir.resolve()),
        *[str(path.resolve()) for path in _java_sources()],
    ]


def compile_java(javac: str, classes_dir: Path) -> None:
    classes_dir.mkdir(parents=True, exist_ok=True)
    command = compile_command(javac, classes_dir)
    subprocess.run(command, cwd=ROOT, check=True)


def java_run_command(
    *,
    java: str,
    classes_dir: Path,
    map_path: Path,
    input_path: Path,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    run_dir: Path,
    fault_schedule: str = "none",
    speed_mps: float | None = None,
) -> list[str]:
    # One repeat per process keeps route/release/output artifacts from the same run.
    command = [
        java,
        "-Djava.awt.headless=true",
        "-cp",
        str(classes_dir.resolve()),
        "LegacyIcsNoFaultWindowBenchmark",
        str(map_path.resolve()),
        str(input_path.resolve()),
        str(start_epoch),
        str(max_epochs),
        str(max_new_tasks),
        "1",
        "0",
        str((run_dir / "routes.csv").resolve()),
        str((run_dir / "summary.csv").resolve()),
        fault_schedule,
        "0",
        "0",
        str((run_dir / "release.csv").resolve()),
    ]
    # Keep the historical direct-call shape when no speed is supplied.  The
    # CLI always supplies its explicit/default speed as the optional tail arg.
    if speed_mps is not None:
        command.append(str(speed_mps))
    return command


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _completed_run(run_dir: Path) -> bool:
    status = _read_json(run_dir / "run_status.json")
    return status.get("status") == "complete" and all(
        (run_dir / name).exists() for name in ("release.csv", "routes.csv", "summary.csv")
    )


def _cleanup_epoch_files(run_dir: Path) -> bool:
    """Remove only the benchmark's per-epoch task directory."""

    task_dir = run_dir / "task"
    if not task_dir.is_dir():
        return False
    shutil.rmtree(task_dir)
    return True


def _record_cleanup(run_dir: Path, *, requested: bool, removed: bool) -> None:
    status = _read_json(run_dir / "run_status.json")
    status["cleanup_epoch_files_requested"] = requested
    status["cleanup_epoch_files_removed"] = removed
    _write_json(run_dir / "run_status.json", status)


def run_campaign(args: argparse.Namespace) -> int:
    defaults = PROFILE_DEFAULTS[args.profile]
    start_epoch = args.start_epoch if args.start_epoch is not None else defaults["start_epoch"]
    max_epochs = args.max_epochs if args.max_epochs is not None else defaults["max_epochs"]
    max_new_tasks = (
        args.max_new_tasks if args.max_new_tasks is not None else defaults["max_new_tasks"]
    )
    repeats = args.repeats if args.repeats is not None else defaults["repeats"]
    timeout_seconds = (
        args.timeout_seconds
        if args.timeout_seconds is not None
        else defaults["timeout_seconds"]
    )
    if repeats < 1 or max_epochs < 1 or max_new_tasks < 0 or timeout_seconds < 0:
        raise FreshHcaError("repeats/max_epochs must be positive; limits cannot be negative")
    if not math.isfinite(args.speed_mps) or args.speed_mps <= 0.0:
        raise FreshHcaError("speed-mps must be finite and positive")

    output_root = args.output_root.resolve()
    commands = [
        (
            output_root / f"run_{index:02d}",
            java_run_command(
                java=args.java,
                classes_dir=args.classes_dir,
                map_path=args.map_path,
                input_path=args.input_path,
                start_epoch=start_epoch,
                max_epochs=max_epochs,
                max_new_tasks=max_new_tasks,
                run_dir=output_root / f"run_{index:02d}",
                fault_schedule=args.fault_schedule,
                speed_mps=args.speed_mps,
            ),
        )
        for index in range(1, repeats + 1)
    ]

    if args.dry_run:
        if not args.skip_compile:
            print(subprocess.list2cmdline(compile_command(args.javac, args.classes_dir)))
        for run_dir, command in commands:
            print(f"cwd={run_dir.resolve()}")
            print(subprocess.list2cmdline(command))
        return 0

    if not args.skip_compile:
        compile_java(args.javac, args.classes_dir)

    output_root.mkdir(parents=True, exist_ok=True)
    for run_dir, command in commands:
        run_dir.mkdir(parents=True, exist_ok=True)
        if not args.force and _completed_run(run_dir):
            print(f"resume: keeping completed {run_dir.name}")
            aggregate_run(run_dir, args.canonical_input)
            if args.cleanup_epoch_files:
                removed = _cleanup_epoch_files(run_dir)
                _record_cleanup(run_dir, requested=True, removed=removed)
            continue

        status: dict[str, Any] = {
            "schema": "g4irsf24.fresh_hca.run.v1",
            "run_id": run_dir.name,
            "profile": args.profile,
            "status": "running",
            "started_at": _utc_now(),
            "cwd": str(run_dir.resolve()),
            "command": command,
            "start_epoch": start_epoch,
            "max_epochs": max_epochs,
            "max_new_tasks": max_new_tasks,
            "fault_schedule": args.fault_schedule,
            "speed_mps": args.speed_mps,
            "cleanup_epoch_files_requested": args.cleanup_epoch_files,
            "cleanup_epoch_files_removed": False,
        }
        _write_json(run_dir / "run_status.json", status)
        started = time.perf_counter()
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
            stdout = completed.stdout
            stderr = completed.stderr
            status["returncode"] = completed.returncode
            status["status"] = "complete" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            status["returncode"] = None
            status["status"] = "timeout"
        except KeyboardInterrupt:
            status["returncode"] = None
            status["status"] = "interrupted"
            status["wall_seconds"] = time.perf_counter() - started
            status["finished_at"] = _utc_now()
            _write_json(run_dir / "run_status.json", status)
            raise

        status["wall_seconds"] = time.perf_counter() - started
        status["finished_at"] = _utc_now()
        (run_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        _write_json(run_dir / "run_status.json", status)

        if status["status"] != "complete":
            print(f"{run_dir.name}: {status['status']}; rerun the same command to resume the campaign")
            aggregate_campaign(output_root, args.canonical_input)
            return 1

        metrics = aggregate_run(run_dir, args.canonical_input)
        if args.cleanup_epoch_files:
            removed = _cleanup_epoch_files(run_dir)
            _record_cleanup(run_dir, requested=True, removed=removed)
        print(
            f"{run_dir.name}: released={metrics['released_segment_count']} "
            f"completed={metrics['completed_segment_count']} "
            f"eligible={metrics['comparison_eligible']} "
            f"wall={metrics['wall_seconds']:.3f}s"
        )

    aggregate_campaign(output_root, args.canonical_input)
    return 0


def _existing_executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise FreshHcaError(f"required executable is not on PATH: {name}")
    return found


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile", help="compile the external Java wrapper")
    compile_parser.add_argument("--javac", default=_existing_executable("javac"))
    compile_parser.add_argument("--classes-dir", type=Path, default=DEFAULT_CLASSES)

    run_parser = subparsers.add_parser("run", help="run a bounded or full fresh HCA campaign")
    run_parser.add_argument("--profile", choices=tuple(PROFILE_DEFAULTS), default="bounded")
    run_parser.add_argument("--map-path", type=Path, default=DEFAULT_MAP)
    run_parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT)
    run_parser.add_argument("--canonical-input", type=Path, default=DEFAULT_CANONICAL)
    run_parser.add_argument("--classes-dir", type=Path, default=DEFAULT_CLASSES)
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    run_parser.add_argument("--java", default=_existing_executable("java"))
    run_parser.add_argument("--javac", default=_existing_executable("javac"))
    run_parser.add_argument("--start-epoch", type=int)
    run_parser.add_argument("--max-epochs", type=int)
    run_parser.add_argument("--max-new-tasks", type=int)
    run_parser.add_argument("--repeats", type=int)
    run_parser.add_argument("--timeout-seconds", type=int)
    run_parser.add_argument("--speed-mps", type=float, default=2.5)
    run_parser.add_argument("--fault-schedule", default="none")
    run_parser.add_argument("--cleanup-epoch-files", action="store_true")
    run_parser.add_argument("--skip-compile", action="store_true")
    run_parser.add_argument("--force", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")

    aggregate_parser = subparsers.add_parser(
        "aggregate", help="rebuild lifecycle and campaign tables from completed run directories"
    )
    aggregate_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    aggregate_parser.add_argument("--canonical-input", type=Path, default=DEFAULT_CANONICAL)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "compile":
        compile_java(args.javac, args.classes_dir)
        print(args.classes_dir.resolve())
        return 0
    if args.command == "aggregate":
        campaign = aggregate_campaign(args.output_root.resolve(), args.canonical_input)
        print(
            f"runs={campaign['run_count']} "
            f"eligible={campaign['comparison_eligible_run_count']}"
        )
        return 0
    return run_campaign(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FreshHcaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
