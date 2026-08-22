#!/usr/bin/env python3
"""Run the original Java HCA* baseline on the frozen G31 Nanning workloads.

This module is only an orchestration layer.  The HCA* implementation, Java
compilation, fixed-window execution, lifecycle alignment, and repeat resume
remain owned by :mod:`run_g4irsf24_fresh_hca`.  G31 supplies a selectable map,
the projected 1x/2x baggage populations, and the map-specific storage role.

The default campaign contains the thesis Table-5.2 speed axis only: two
workload scales times four speeds, with two independent processes per case.
The frozen G31 interruption protocol can also be loaded explicitly with
``--include-faults`` and retains the paper-campaign convention of one process
per interruption case; merely aggregating or dry-running the default campaign
does not start those cases.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import io
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf24_fresh_hca as g24  # noqa: E402


TASK_DIR = ROOT / "artifacts" / "tasks" / "g4irsf31_nanning"
DEFAULT_MAP = ROOT / "data" / "processed" / "maps" / "nanning_legacy.txt"
DEFAULT_FAULT_PROTOCOL = (
    ROOT / "configs" / "eval" / "g4irsf31_nanning_fault_scenarios.json"
)
DEFAULT_CLASSES_DIR = ROOT / "build" / "g4irsf31_nanning_java"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "runtime" / "g4irsf31_nanning_hca"
DEFAULT_AGGREGATE_JSON = ROOT / "outputs" / "tables" / "g4irsf31_nanning_hca.json"
DEFAULT_AGGREGATE_CSV = ROOT / "outputs" / "tables" / "g4irsf31_nanning_hca.csv"

WORKLOAD_SCHEMA = "czr005.g4irsf31.nanning_workload_manifest.v1"
CAMPAIGN_SCHEMA = "czr005.g4irsf31.nanning_hca_campaign.v1"
CASE_PROTOCOL_SCHEMA = "czr005.g4irsf31.nanning_hca_case_protocol.v1"
FAULT_PROTOCOL_SCHEMA = "czr005.g4irsf31.nanning_experiment_protocol.v1"

START_EPOCH = 8_260
MAX_EPOCHS = 90_000
END_EPOCH = START_EPOCH + MAX_EPOCHS - 1
MAX_NEW_TASKS = 0
STABLE_REPEATS = 2
FAULT_REPEATS = 1
SPEEDS = (1.5, 2.0, 2.5, 3.0)
SCALES = (1, 2)
EXPECTED_POPULATIONS = {
    1: (28_506, 43_603),
    2: (57_012, 87_206),
}


class G31NanningHcaError(RuntimeError):
    """Raised when the small G31 campaign contract is inconsistent."""


@dataclass(frozen=True)
class Workload:
    scale: int
    raw_input: Path
    canonical_input: Path
    manifest_path: Path
    raw_task_count: int
    expanded_segment_count: int
    storage_in_goal: int
    storage_out_start: int
    early_threshold_seconds: float
    storage_lead_seconds: float
    map_id: str


@dataclass(frozen=True)
class HcaCase:
    case_id: str
    scale: int
    case_group: str
    repeats: int
    speed_mps: float
    fault_line_ids: tuple[int, ...] = ()
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_schedule: str = "none"
    topology_upper_raw_bags: int | None = None


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _speed_token(speed: float) -> str:
    return f"{speed:g}".replace(".", "p")


def speed_cases(scales: Sequence[int] = SCALES) -> tuple[HcaCase, ...]:
    return tuple(
        HcaCase(
            case_id=f"nanning_{scale}x_t5_2_speed_{_speed_token(speed)}",
            scale=scale,
            case_group="stable_speed",
            repeats=STABLE_REPEATS,
            speed_mps=speed,
        )
        for scale in scales
        for speed in SPEEDS
    )


def fault_cases(
    protocol_path: Path = DEFAULT_FAULT_PROTOCOL,
    scales: Sequence[int] = SCALES,
) -> tuple[HcaCase, ...]:
    """Load map-specific Table-5.5 cases without consulting algorithm results."""

    path = _rooted(protocol_path).resolve()
    if not path.is_file():
        raise G31NanningHcaError(f"missing G31 interruption protocol: {path}")
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("schema") != FAULT_PROTOCOL_SCHEMA:
        raise G31NanningHcaError("unexpected G31 interruption protocol schema")

    cases: list[HcaCase] = []
    for scale in scales:
        scale_row = (protocol.get("scales") or {}).get(f"{scale}x")
        if not isinstance(scale_row, Mapping):
            raise G31NanningHcaError(f"fault protocol has no {scale}x population")
        for row in scale_row.get("scenarios", []):
            scenario = str(row["scenario"])
            edges = tuple(
                (int(edge[0]), int(edge[1])) for edge in row.get("fault_edges", [])
            )
            schedule = ";".join(
                f"{START_EPOCH}:{start}:{end}:fault" for start, end in edges
            )
            cases.append(
                HcaCase(
                    case_id=f"nanning_{scale}x_t5_5_fault_{scenario}",
                    scale=scale,
                    case_group="all_day_line_interruption",
                    repeats=FAULT_REPEATS,
                    speed_mps=2.5,
                    fault_line_ids=tuple(int(value) for value in row["line_ids"]),
                    fault_edges=edges,
                    fault_schedule=schedule or "none",
                    topology_upper_raw_bags=int(row["topology_upper_raw_bags"]),
                )
            )
    return tuple(cases)


def hca_cases(
    *,
    include_faults: bool = False,
    fault_protocol: Path = DEFAULT_FAULT_PROTOCOL,
    scales: Sequence[int] = SCALES,
) -> tuple[HcaCase, ...]:
    values = list(speed_cases(scales))
    if include_faults:
        values.extend(fault_cases(fault_protocol, scales))
    return tuple(values)


def case_by_id(case_id: str, cases: Sequence[HcaCase]) -> HcaCase:
    for case in cases:
        if case.case_id == case_id:
            return case
    raise G31NanningHcaError(f"unknown G31 Nanning HCA case: {case_id}")


def _count_nonempty_lines(path: Path, *, skip_header: bool = False) -> int:
    with path.open("r", encoding="utf-8") as handle:
        count = sum(bool(line.strip()) for line in handle)
    return count - int(skip_header)


def load_workload(task_dir: Path, scale: int) -> Workload:
    if scale not in SCALES:
        raise G31NanningHcaError(f"unsupported Nanning scale: {scale}")
    directory = _rooted(task_dir).resolve()
    raw = directory / f"nanning_{scale}x_raw.txt"
    canonical = directory / f"nanning_{scale}x_canonical.jsonl"
    manifest_path = directory / f"nanning_{scale}x_manifest.json"
    for path in (raw, canonical, manifest_path):
        if not path.is_file():
            raise G31NanningHcaError(f"missing G31 {scale}x workload file: {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != WORKLOAD_SCHEMA
        or manifest.get("status") != "COMPLETE"
        or int(manifest.get("scale", -1)) != scale
    ):
        raise G31NanningHcaError(f"G31 {scale}x workload manifest is not COMPLETE")
    raw_count = int(manifest["raw_task_count"])
    segment_count = int(manifest["expanded_segment_count"])
    if (raw_count, segment_count) != EXPECTED_POPULATIONS[scale]:
        raise G31NanningHcaError(f"G31 {scale}x manifest has an unexpected population")
    if _count_nonempty_lines(raw, skip_header=True) != raw_count:
        raise G31NanningHcaError(f"G31 {scale}x raw row count does not match its manifest")
    if _count_nonempty_lines(canonical) != segment_count:
        raise G31NanningHcaError(
            f"G31 {scale}x canonical row count does not match its manifest"
        )

    lifecycle = manifest["lifecycle"]
    storage_in = int(lifecycle["storage_in_goal"])
    storage_out = int(lifecycle["storage_out_start"])
    if storage_in != storage_out:
        raise G31NanningHcaError("G31 Nanning storage proxy must use one frozen node")
    return Workload(
        scale=scale,
        raw_input=raw,
        canonical_input=canonical,
        manifest_path=manifest_path,
        raw_task_count=raw_count,
        expanded_segment_count=segment_count,
        storage_in_goal=storage_in,
        storage_out_start=storage_out,
        early_threshold_seconds=float(lifecycle["early_bag_threshold_seconds"]),
        storage_lead_seconds=float(lifecycle["storage_out_lead_seconds"]),
        map_id=str(manifest["map_id"]),
    )


def load_workloads(task_dir: Path, scales: Sequence[int]) -> dict[int, Workload]:
    return {scale: load_workload(task_dir, scale) for scale in scales}


def _case_root(output_root: Path, case: HcaCase) -> Path:
    return _rooted(output_root).resolve() / case.case_id


def _java_commands(
    case: HcaCase,
    workload: Workload,
    *,
    map_path: Path,
    classes_dir: Path,
    output_root: Path,
    java: str,
) -> list[list[str]]:
    root = _case_root(output_root, case)
    return [
        g24.java_run_command(
            java=java,
            classes_dir=_rooted(classes_dir),
            map_path=_rooted(map_path),
            input_path=workload.raw_input,
            start_epoch=START_EPOCH,
            max_epochs=MAX_EPOCHS,
            max_new_tasks=MAX_NEW_TASKS,
            run_dir=root / f"run_{repeat:02d}",
            fault_schedule=case.fault_schedule,
            speed_mps=case.speed_mps,
            storage_in_goal=workload.storage_in_goal,
            storage_out_start=workload.storage_out_start,
            early_threshold_seconds=workload.early_threshold_seconds,
            storage_lead_seconds=workload.storage_lead_seconds,
        )
        for repeat in range(1, case.repeats + 1)
    ]


def dry_run_payload(
    args: argparse.Namespace,
    workloads: Mapping[int, Workload],
    cases: Sequence[HcaCase],
) -> dict[str, Any]:
    return {
        "schema": CAMPAIGN_SCHEMA,
        "status": "DRY_RUN_NO_CASE_STARTED",
        "protocol": {
            "start_epoch": START_EPOCH,
            "max_epochs": MAX_EPOCHS,
            "end_epoch": END_EPOCH,
            "max_new_tasks": MAX_NEW_TASKS,
            "stable_repeats_per_case": STABLE_REPEATS,
            "fault_repeats_per_case": FAULT_REPEATS,
            "process_count": sum(case.repeats for case in cases),
            "fixed_raw_bag_denominator": True,
            "timing_claim": "FULL_POPULATION_ONLY",
            "case_count": len(cases),
        },
        "workloads": {
            f"{scale}x": _workload_payload(workload)
            for scale, workload in sorted(workloads.items())
        },
        "map_path": _display_path(_rooted(args.map_path)),
        "compile_command": g24.compile_command(args.javac, _rooted(args.classes_dir)),
        "cases": [
            {
                **asdict(case),
                "commands": _java_commands(
                    case,
                    workloads[case.scale],
                    map_path=args.map_path,
                    classes_dir=args.classes_dir,
                    output_root=args.output_root,
                    java=args.java,
                ),
            }
            for case in cases
        ],
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    target = _rooted(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _workload_payload(workload: Workload) -> dict[str, Any]:
    return {
        "scale": workload.scale,
        "manifest": _display_path(workload.manifest_path),
        "raw_input": _display_path(workload.raw_input),
        "canonical_input": _display_path(workload.canonical_input),
        "raw_task_count": workload.raw_task_count,
        "expanded_segment_count": workload.expanded_segment_count,
        "storage_in_goal": workload.storage_in_goal,
        "storage_out_start": workload.storage_out_start,
        "map_id": workload.map_id,
    }


def _write_case_protocol(case_root: Path, case: HcaCase, workload: Workload) -> None:
    _write_json(
        case_root / "case_protocol.json",
        {
            "schema": CASE_PROTOCOL_SCHEMA,
            "case": asdict(case),
            "workload": _workload_payload(workload),
            "fixed_window": {
                "start_epoch": START_EPOCH,
                "max_epochs": MAX_EPOCHS,
                "end_epoch": END_EPOCH,
            },
            "claim_boundary": (
                "FIXED_POPULATION_TIMING_ONLY_IF_ALL_BAGS_COMPLETE"
                if case.case_group == "stable_speed"
                else "FIXED_POPULATION_CAPACITY_ONLY"
            ),
        },
    )


def _runner_namespace(
    args: argparse.Namespace,
    workload: Workload,
    case: HcaCase,
    *,
    skip_compile: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        profile="full",
        map_path=_rooted(args.map_path),
        input_path=workload.raw_input,
        canonical_input=workload.canonical_input,
        classes_dir=_rooted(args.classes_dir),
        output_root=_case_root(args.output_root, case),
        java=args.java,
        javac=args.javac,
        start_epoch=START_EPOCH,
        max_epochs=MAX_EPOCHS,
        max_new_tasks=MAX_NEW_TASKS,
        repeats=case.repeats,
        timeout_seconds=args.timeout_seconds,
        speed_mps=case.speed_mps,
        storage_in_goal=workload.storage_in_goal,
        storage_out_start=workload.storage_out_start,
        early_threshold_seconds=workload.early_threshold_seconds,
        storage_lead_seconds=workload.storage_lead_seconds,
        fault_schedule=case.fault_schedule,
        cleanup_epoch_files=True,
        skip_compile=skip_compile,
        force=args.force,
        dry_run=False,
    )


def run_case(
    args: argparse.Namespace,
    workload: Workload,
    case: HcaCase,
    *,
    skip_compile: bool | None = None,
) -> int:
    case_root = _case_root(args.output_root, case)
    case_root.mkdir(parents=True, exist_ok=True)
    _write_case_protocol(case_root, case, workload)
    return g24.run_campaign(
        _runner_namespace(
            args,
            workload,
            case,
            skip_compile=args.skip_compile if skip_compile is None else skip_compile,
        )
    )


def _number(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _status_matches(run_dir: Path, case: HcaCase, workload: Workload) -> bool:
    path = run_dir / "run_status.json"
    if not path.is_file():
        return False
    status = json.loads(path.read_text(encoding="utf-8"))
    return bool(
        status.get("status") == "complete"
        and _number(status.get("start_epoch")) == START_EPOCH
        and _number(status.get("max_epochs")) == MAX_EPOCHS
        and math.isclose(float(status.get("speed_mps", -1)), case.speed_mps)
        and status.get("fault_schedule") == case.fault_schedule
        and _number(status.get("storage_in_goal")) == workload.storage_in_goal
        and _number(status.get("storage_out_start")) == workload.storage_out_start
    )


def _timing_distribution(run: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = (((run.get("denominators") or {}).get("processed_attempt") or {}).get("minutes"))
    return dict(value) if isinstance(value, Mapping) else None


def _complete_case_row(
    case: HcaCase,
    workload: Workload,
    case_root: Path,
) -> dict[str, Any]:
    campaign = g24.aggregate_campaign(case_root, workload.canonical_input)
    runs = list(campaign.get("runs", []))
    run_dirs = [case_root / f"run_{repeat:02d}" for repeat in range(1, case.repeats + 1)]
    status_pass = len(runs) == case.repeats and all(
        _status_matches(run_dir, case, workload) for run_dir in run_dirs
    )
    cohort_pass = len(runs) == case.repeats and all(
        _number(run.get("canonical_segment_count")) == workload.expanded_segment_count
        and _number(run.get("canonical_raw_bag_count")) == workload.raw_task_count
        for run in runs
    )
    horizon_pass = len(runs) == case.repeats and all(
        _number((run.get("benchmark_summary") or {}).get("epochs_run")) == MAX_EPOCHS
        for run in runs
    )
    fault_pass = case.case_group == "stable_speed" or all(
        _number((run.get("benchmark_summary") or {}).get("fault_event_count"))
        == len(case.fault_edges)
        and _number((run.get("benchmark_summary") or {}).get("repair_event_count")) == 0
        for run in runs
    )
    capacity_eligible = bool(status_pass and cohort_pass and horizon_pass and fault_pass)

    def values(name: str) -> list[Any]:
        return [run.get(name) for run in runs]

    complete_bags = values("canonical_complete_raw_bag_count")
    completion_rates = [
        (float(value) / workload.raw_task_count) if isinstance(value, int) else None
        for value in complete_bags
    ]
    full_population = bool(
        capacity_eligible
        and all(run.get("comparison_eligible") is True for run in runs)
        and all(value == workload.raw_task_count for value in complete_bags)
        and all(
            _number(run.get("released_segment_count")) == workload.expanded_segment_count
            and _number(run.get("planned_segment_count")) == workload.expanded_segment_count
            and _number(run.get("completed_segment_count")) == workload.expanded_segment_count
            for run in runs
        )
    )
    formal_timing = bool(full_population and case.case_group == "stable_speed")
    distributions = [_timing_distribution(run) for run in runs]
    means = [
        value.get("mean") if isinstance(value, Mapping) else None
        for value in distributions
    ]
    valid_rates = [value for value in completion_rates if value is not None]

    return {
        "case_id": case.case_id,
        "scale": case.scale,
        "case_group": case.case_group,
        "protocol_status": (
            "FULL_POPULATION_TIMING"
            if formal_timing
            else "FIXED_HORIZON_CAPACITY"
            if capacity_eligible
            else "INVALID"
        ),
        "repeats_expected": case.repeats,
        "repeats_complete": len(runs),
        "speed_mps": case.speed_mps,
        "fault_line_ids": list(case.fault_line_ids),
        "fault_edges": [list(edge) for edge in case.fault_edges],
        "fault_schedule": case.fault_schedule,
        "topology_upper_raw_bags": case.topology_upper_raw_bags,
        "fixed_raw_bag_denominator": workload.raw_task_count,
        "fixed_segment_population": workload.expanded_segment_count,
        "primary_capacity_eligible": capacity_eligible,
        "status_echo_pass": status_pass,
        "cohort_pass": cohort_pass,
        "fixed_horizon_pass": horizon_pass,
        "fault_event_pass": fault_pass,
        "released_segment_count_by_repeat": values("released_segment_count"),
        "planned_segment_count_by_repeat": values("planned_segment_count"),
        "completed_segment_count_by_repeat": values("completed_segment_count"),
        "completed_raw_bag_count_by_repeat": complete_bags,
        "fixed_denominator_completion_rate_by_repeat": completion_rates,
        "mean_fixed_denominator_completion_rate": (
            statistics.fmean(valid_rates) if valid_rates else None
        ),
        "full_population_completion": full_population,
        "formal_timing_comparison_allowed": formal_timing,
        "timing_scope": "FULL_POPULATION" if formal_timing else "NOT_REPORTED",
        "processed_attempt_mean_minutes_by_repeat": (
            means if formal_timing else [None for _ in runs]
        ),
        "full_population_processed_attempt_minutes_by_repeat": (
            distributions if formal_timing else [None for _ in runs]
        ),
    }


def aggregate_campaign(
    workloads: Mapping[int, Workload],
    output_root: Path,
    cases: Sequence[HcaCase],
) -> dict[str, Any]:
    root = _rooted(output_root).resolve()
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    invalid: list[str] = []
    for case in cases:
        workload = workloads[case.scale]
        case_root = root / case.case_id
        complete = sum(
            g24._completed_run(case_root / f"run_{repeat:02d}")
            for repeat in range(1, case.repeats + 1)
        )
        if complete != case.repeats:
            rows.append(
                {
                    "case_id": case.case_id,
                    "scale": case.scale,
                    "case_group": case.case_group,
                    "protocol_status": "MISSING_OR_PARTIAL",
                    "repeats_expected": case.repeats,
                    "repeats_complete": complete,
                    "speed_mps": case.speed_mps,
                    "fixed_raw_bag_denominator": workload.raw_task_count,
                    "fixed_segment_population": workload.expanded_segment_count,
                    "primary_capacity_eligible": False,
                    "formal_timing_comparison_allowed": False,
                    "timing_scope": "NOT_REPORTED",
                }
            )
            missing.append(case.case_id)
            continue
        row = _complete_case_row(case, workload, case_root)
        rows.append(row)
        if not row["primary_capacity_eligible"]:
            invalid.append(case.case_id)

    return {
        "schema": CAMPAIGN_SCHEMA,
        "status": "COMPLETE" if not missing and not invalid else "PARTIAL_OR_INVALID",
        "map_path": _display_path(DEFAULT_MAP),
        "workloads": {
            f"{scale}x": _workload_payload(workload)
            for scale, workload in sorted(workloads.items())
        },
        "protocol": {
            "start_epoch": START_EPOCH,
            "max_epochs": MAX_EPOCHS,
            "end_epoch": END_EPOCH,
            "stable_repeats_per_case": STABLE_REPEATS,
            "fault_repeats_per_case": FAULT_REPEATS,
            "expected_process_count": sum(case.repeats for case in cases),
            "fixed_raw_bag_denominator": True,
            "timing_claim": "FULL_POPULATION_ONLY",
            "partial_completion_claim": "FIXED_HORIZON_CAPACITY_ONLY",
            "expected_case_count": len(cases),
        },
        "complete_case_count": len(cases) - len(missing) - len(invalid),
        "missing_case_ids": missing,
        "invalid_case_ids": invalid,
        "rows": rows,
    }


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (list, dict, tuple))
                else value
                for key, value in row.items()
            }
        )
    return stream.getvalue()


def write_aggregate(value: Mapping[str, Any], json_path: Path, csv_path: Path) -> None:
    _write_json(json_path, value)
    target = _rooted(csv_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_csv_text(value["rows"]), encoding="utf-8")


def _add_common(parser: argparse.ArgumentParser, *, runtime: bool) -> None:
    parser.add_argument("--task-dir", type=Path, default=TASK_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--scale", type=int, choices=SCALES, action="append")
    parser.add_argument("--include-faults", action="store_true")
    parser.add_argument("--fault-protocol", type=Path, default=DEFAULT_FAULT_PROTOCOL)
    if runtime:
        parser.add_argument("--map-path", type=Path, default=DEFAULT_MAP)
        parser.add_argument("--classes-dir", type=Path, default=DEFAULT_CLASSES_DIR)
        parser.add_argument("--java", default="java")
        parser.add_argument("--javac", default="javac")
        parser.add_argument("--timeout-seconds", type=int, default=0)
        parser.add_argument("--skip-compile", action="store_true")
        parser.add_argument("--force", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    dry = commands.add_parser("dry-run", help="describe commands without starting Java")
    _add_common(dry, runtime=True)
    dry.add_argument("--output-json", type=Path)

    case = commands.add_parser("case", help="run or resume one isolated case")
    _add_common(case, runtime=True)
    case.add_argument("--case-id", required=True)
    case.add_argument("--aggregate-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    case.add_argument("--aggregate-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)

    resume = commands.add_parser("resume", help="run selected cases in registry order")
    _add_common(resume, runtime=True)
    resume.add_argument("--case-id", action="append")
    resume.add_argument("--aggregate-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    resume.add_argument("--aggregate-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)

    aggregate = commands.add_parser("aggregate", help="aggregate existing cases only")
    _add_common(aggregate, runtime=False)
    aggregate.add_argument("--output-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    aggregate.add_argument("--output-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scales = tuple(dict.fromkeys(args.scale or SCALES))
    workloads = load_workloads(args.task_dir, scales)
    cases = hca_cases(
        include_faults=args.include_faults,
        fault_protocol=args.fault_protocol,
        scales=scales,
    )

    if args.command == "dry-run":
        value = dry_run_payload(args, workloads, cases)
        if args.output_json is not None:
            _write_json(args.output_json, value)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0

    if args.command == "aggregate":
        value = aggregate_campaign(workloads, args.output_root, cases)
        write_aggregate(value, args.output_json, args.output_csv)
        print(json.dumps({"status": value["status"], "complete_case_count": value["complete_case_count"]}))
        return 0 if value["status"] == "COMPLETE" else 2

    if args.command == "case":
        selected = case_by_id(args.case_id, cases)
        status = run_case(args, workloads[selected.scale], selected)
        value = aggregate_campaign(workloads, args.output_root, cases)
        write_aggregate(value, args.aggregate_json, args.aggregate_csv)
        return status

    if args.command == "resume":
        selected_ids = set(args.case_id or [])
        selected_cases = [
            case for case in cases if not selected_ids or case.case_id in selected_ids
        ]
        unknown = selected_ids - {case.case_id for case in cases}
        if unknown:
            raise G31NanningHcaError(f"unknown case IDs: {sorted(unknown)}")
        if selected_cases and not args.skip_compile:
            g24.compile_java(args.javac, _rooted(args.classes_dir))
        for selected in selected_cases:
            status = run_case(
                args, workloads[selected.scale], selected, skip_compile=True
            )
            if status != 0:
                return status
        value = aggregate_campaign(workloads, args.output_root, cases)
        write_aggregate(value, args.aggregate_json, args.aggregate_csv)
        return 0 if not value["invalid_case_ids"] else 2

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (G31NanningHcaError, g24.FreshHcaError) as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
