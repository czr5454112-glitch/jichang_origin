#!/usr/bin/env python3
"""Run the original Java HCA* baseline on the frozen G29 2x workload.

This module is intentionally an orchestration layer.  It reuses the G24 Java
runner for compilation, execution, lifecycle alignment, and repeat-level
resume, and it reuses the G26 Chapter-5 registry for speeds and interruption
identity.  No HCA* or Java scheduling logic is copied here.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf24_fresh_hca as g24
from scripts.eval import run_g4irsf26_paper_experiments as g26


WORKLOAD_DIR = ROOT / "artifacts" / "tasks" / "g4irsf29"
DEFAULT_RAW_INPUT = WORKLOAD_DIR / "inputdata_flight_densified_2x.txt"
DEFAULT_CANONICAL_INPUT = WORKLOAD_DIR / "inputdata_flight_densified_2x.jsonl"
DEFAULT_WORKLOAD_MANIFEST = WORKLOAD_DIR / "g4irsf29_workload_manifest.json"
DEFAULT_CLASSES_DIR = ROOT / "build" / "g4irsf29_java"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "runtime" / "g4irsf29_hca"
DEFAULT_AGGREGATE_JSON = ROOT / "outputs" / "tables" / "g4irsf29_hca.json"
DEFAULT_AGGREGATE_CSV = ROOT / "outputs" / "tables" / "g4irsf29_hca.csv"

WORKLOAD_SCHEMA = "czr005.g4irsf29.workload_manifest.v1"
CAMPAIGN_SCHEMA = "czr005.g4irsf29.hca_campaign.v1"
CASE_PROTOCOL_SCHEMA = "czr005.g4irsf29.hca_case_protocol.v1"

START_EPOCH = 8_260
MAX_EPOCHS = 90_000
END_EPOCH = START_EPOCH + MAX_EPOCHS - 1
MAX_NEW_TASKS = 0


class G29HcaError(RuntimeError):
    """Raised when the 2x workload or an HCA campaign is inconsistent."""


@dataclass(frozen=True)
class Workload:
    raw_input: Path
    canonical_input: Path
    manifest_path: Path
    raw_task_count: int
    expanded_segment_count: int
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class HcaCase:
    case_id: str
    case_group: str
    repeats: int
    speed_mps: float
    fault_line_ids: tuple[int, ...]
    seed_edges: tuple[tuple[int, int], ...]
    fault_schedule: str
    execution_class: str
    protocol_fidelity: str

    @property
    def archived_only(self) -> bool:
        return self.execution_class == "ARCHIVED_ONLY_PROBE"


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _display_path(path: Path) -> str:
    """Keep published evidence portable while accepting absolute CLI inputs."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def hca_cases() -> tuple[HcaCase, ...]:
    """Return the 4-speed plus 16-interruption registry from G26."""

    cases: list[HcaCase] = []
    for source in g26.paper_cases():
        group = str(source["case_group"])
        if group not in {"stable_speed", "all_day_line_interruption"}:
            continue
        edges = tuple(tuple(int(part) for part in edge) for edge in source["seed_edges"])
        archived = bool(source.get("case_specific_seed_edge_override"))
        schedule = (
            ";".join(f"{START_EPOCH}:{start}:{end}:fault" for start, end in edges)
            if edges
            else "none"
        )
        cases.append(
            HcaCase(
                case_id=str(source["case_id"]),
                case_group=group,
                repeats=2 if group == "stable_speed" else 1,
                speed_mps=float(source["actual_speed_mps"]),
                fault_line_ids=tuple(int(value) for value in source["fault_line_ids"]),
                seed_edges=edges,
                fault_schedule=schedule,
                execution_class=(
                    "ARCHIVED_ONLY_PROBE" if archived else "PRIMARY_MEASURABLE"
                ),
                protocol_fidelity=str(source["protocol_fidelity"]),
            )
        )
    return tuple(cases)


def case_by_id(case_id: str) -> HcaCase:
    for case in hca_cases():
        if case.case_id == case_id:
            return case
    raise G29HcaError(f"unknown G29 HCA case: {case_id}")


def load_workload(
    raw_input: Path,
    canonical_input: Path,
    manifest_path: Path,
) -> Workload:
    """Load the small G29 contract and check the two views describe one cohort."""

    raw_path = _rooted(raw_input).resolve()
    canonical_path = _rooted(canonical_input).resolve()
    manifest_file = _rooted(manifest_path).resolve()
    for path in (raw_path, canonical_path, manifest_file):
        if not path.is_file():
            raise G29HcaError(f"missing G29 workload file: {path}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema") != WORKLOAD_SCHEMA or manifest.get("status") != "COMPLETE":
        raise G29HcaError("G29 workload manifest is not COMPLETE under the frozen schema")
    raw_expected = int(manifest["raw_task_count"])
    expanded_expected = int(manifest["expanded_segment_count"])

    raw_lines = [
        line
        for line in raw_path.read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    ]
    raw_ids = [int(line.split()[0]) for line in raw_lines]
    if len(raw_lines) != raw_expected or len(set(raw_ids)) != raw_expected:
        raise G29HcaError("G29 raw row count or task_ID uniqueness does not match its manifest")

    canonical_count = 0
    canonical_task_ids: set[int] = set()
    with canonical_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            canonical_count += 1
            canonical_task_ids.add(int(row["task_id"]))
    if canonical_count != expanded_expected or canonical_task_ids != set(raw_ids):
        raise G29HcaError("G29 canonical segments do not match the raw 2x bag cohort")

    return Workload(
        raw_input=raw_path,
        canonical_input=canonical_path,
        manifest_path=manifest_file,
        raw_task_count=raw_expected,
        expanded_segment_count=expanded_expected,
        manifest=manifest,
    )


def _case_output_root(output_root: Path, case: HcaCase) -> Path:
    return _rooted(output_root).resolve() / case.case_id


def _java_commands(
    case: HcaCase,
    *,
    workload: Workload,
    map_path: Path,
    classes_dir: Path,
    output_root: Path,
    java: str,
) -> list[list[str]]:
    case_root = _case_output_root(output_root, case)
    return [
        g24.java_run_command(
            java=java,
            classes_dir=_rooted(classes_dir),
            map_path=_rooted(map_path),
            input_path=workload.raw_input,
            start_epoch=START_EPOCH,
            max_epochs=MAX_EPOCHS,
            max_new_tasks=MAX_NEW_TASKS,
            run_dir=case_root / f"run_{repeat:02d}",
            fault_schedule=case.fault_schedule,
            speed_mps=case.speed_mps,
        )
        for repeat in range(1, case.repeats + 1)
    ]


def dry_run_payload(args: argparse.Namespace, workload: Workload) -> dict[str, Any]:
    cases = []
    for case in hca_cases():
        cases.append(
            {
                **asdict(case),
                "archived_only": case.archived_only,
                "output_root": str(_case_output_root(args.output_root, case)),
                "commands": _java_commands(
                    case,
                    workload=workload,
                    map_path=args.map_path,
                    classes_dir=args.classes_dir,
                    output_root=args.output_root,
                    java=args.java,
                ),
            }
        )
    return {
        "schema": CAMPAIGN_SCHEMA,
        "status": "DRY_RUN_NO_CASE_STARTED",
        "workload": {
            "manifest": str(workload.manifest_path),
            "raw_input": str(workload.raw_input),
            "canonical_input": str(workload.canonical_input),
            "raw_task_count": workload.raw_task_count,
            "expanded_segment_count": workload.expanded_segment_count,
        },
        "protocol": {
            "start_epoch": START_EPOCH,
            "max_epochs": MAX_EPOCHS,
            "end_epoch": END_EPOCH,
            "max_new_tasks": MAX_NEW_TASKS,
            "cleanup_epoch_files": True,
            "speed_case_count": 4,
            "fault_case_count": 16,
            "primary_executable_case_count": 19,
            "archived_only_probe_case_ids": [
                case.case_id for case in hca_cases() if case.archived_only
            ],
        },
        "compile_command": g24.compile_command(args.javac, _rooted(args.classes_dir)),
        "cases": cases,
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    target = _rooted(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _write_case_protocol(case_root: Path, case: HcaCase, workload: Workload) -> None:
    _write_json(
        case_root / "case_protocol.json",
        {
            "schema": CASE_PROTOCOL_SCHEMA,
            "case": asdict(case),
            "workload": {
                "manifest": _display_path(workload.manifest_path),
                "raw_input": _display_path(workload.raw_input),
                "canonical_input": _display_path(workload.canonical_input),
                "raw_task_count": workload.raw_task_count,
                "expanded_segment_count": workload.expanded_segment_count,
            },
            "fixed_window": {
                "start_epoch": START_EPOCH,
                "max_epochs": MAX_EPOCHS,
                "end_epoch": END_EPOCH,
            },
            "claim_boundary": (
                "ARCHIVED_ONLY_WORKBOOK_LABEL_PROBE_NOT_PRIMARY_EVIDENCE"
                if case.archived_only
                else "G29_2X_PRIMARY_HCA"
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
        output_root=_case_output_root(args.output_root, case),
        java=args.java,
        javac=args.javac,
        start_epoch=START_EPOCH,
        max_epochs=MAX_EPOCHS,
        max_new_tasks=MAX_NEW_TASKS,
        repeats=case.repeats,
        timeout_seconds=args.timeout_seconds,
        speed_mps=case.speed_mps,
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
    if case.archived_only and not args.include_archived_probe:
        print(json.dumps({"case_id": case.case_id, "status": "ARCHIVED_ONLY_NOT_EXECUTED"}))
        return 0
    case_root = _case_output_root(args.output_root, case)
    case_root.mkdir(parents=True, exist_ok=True)
    _write_case_protocol(case_root, case, workload)
    runner_args = _runner_namespace(
        args,
        workload,
        case,
        skip_compile=args.skip_compile if skip_compile is None else skip_compile,
    )
    return g24.run_campaign(runner_args)


def _release_projection(path: Path) -> tuple[tuple[str, ...], ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return tuple(
            (
                row["ordinal"],
                row["task_id"],
                row["start"],
                row["goal"],
                row["release_epoch"],
            )
            for row in csv.DictReader(handle)
        )


def _number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run_status_matches(case: HcaCase, run_dir: Path) -> bool:
    value = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    return (
        value.get("status") == "complete"
        and int(value.get("start_epoch", -1)) == START_EPOCH
        and int(value.get("max_epochs", -1)) == MAX_EPOCHS
        and float(value.get("speed_mps", -1.0)) == case.speed_mps
        and value.get("fault_schedule") == case.fault_schedule
    )


def _complete_case_row(case: HcaCase, workload: Workload, case_root: Path) -> dict[str, Any]:
    campaign = g24.aggregate_campaign(case_root, workload.canonical_input)
    runs = list(campaign.get("runs", []))
    expected_dirs = [case_root / f"run_{index:02d}" for index in range(1, case.repeats + 1)]
    status_echo_pass = len(runs) == case.repeats and all(
        _run_status_matches(case, run_dir) for run_dir in expected_dirs
    )
    cohort_pass = len(runs) == case.repeats and all(
        int(run.get("canonical_segment_count", -1)) == workload.expanded_segment_count
        and int(run.get("canonical_raw_bag_count", -1)) == workload.raw_task_count
        for run in runs
    )
    fixed_horizon_pass = status_echo_pass and all(
        _number((run.get("benchmark_summary") or {}).get("epochs_run")) == MAX_EPOCHS
        for run in runs
    )
    release_repeat_match: bool | None = None
    if case.repeats > 1:
        projections = [_release_projection(run_dir / "release.csv") for run_dir in expected_dirs]
        release_repeat_match = all(value == projections[0] for value in projections[1:])

    if case.case_group == "stable_speed":
        full_release_fixed_horizon = (
            fixed_horizon_pass
            and cohort_pass
            and release_repeat_match is True
            and all(
                int(run.get("released_segment_count", -1)) == workload.expanded_segment_count
                for run in runs
            )
        )
        full_completion_eligible = (
            full_release_fixed_horizon
            and all(bool(run.get("comparison_eligible")) for run in runs)
            and all(
                int(run.get("planned_segment_count", -1)) == workload.expanded_segment_count
                and int(run.get("completed_segment_count", -1))
                == workload.expanded_segment_count
                and int(run.get("canonical_complete_raw_bag_count", -1))
                == workload.raw_task_count
                for run in runs
            )
        )
        primary_eligible = full_release_fixed_horizon
        protocol_status = (
            "EXACT_FULL_COMPLETION"
            if full_completion_eligible
            else "EXACT_RELEASE_FULL_POPULATION_FIXED_HORIZON"
            if full_release_fixed_horizon
            else "INVALID_OR_PARTIAL"
        )
    else:
        first = runs[0] if len(runs) == 1 else {}
        benchmark = first.get("benchmark_summary") or {}
        primary_eligible = (
            not case.archived_only
            and status_echo_pass
            and cohort_pass
            and _number(benchmark.get("fault_event_count")) == len(case.seed_edges)
            and _number(benchmark.get("repair_event_count")) == 0
            and _number(benchmark.get("epochs_run")) == MAX_EPOCHS
        )
        protocol_status = (
            "ARCHIVED_ONLY_PROBE_COMPLETE"
            if case.archived_only and status_echo_pass and cohort_pass
            else "FIXED_HORIZON_CAPACITY"
            if primary_eligible
            else "INVALID_OR_PARTIAL"
        )
        full_completion_eligible = False

    def run_values(key: str) -> list[Any]:
        return [run.get(key) for run in runs]

    processed_attempt_distributions = [
        dict(
            ((run.get("denominators") or {}).get("processed_attempt") or {}).get(
                "minutes", {}
            )
        )
        for run in runs
    ]
    processed_attempt_means = [
        distribution.get("mean") for distribution in processed_attempt_distributions
    ]
    wall_seconds_by_repeat = [
        json.loads((run_dir / "run_status.json").read_text(encoding="utf-8")).get(
            "wall_seconds"
        )
        for run_dir in expected_dirs
    ]
    timing_scope = (
        "FULL_POPULATION"
        if full_completion_eligible
        else "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
        if primary_eligible
        else "NOT_ADMITTED"
    )

    return {
        "case_id": case.case_id,
        "case_group": case.case_group,
        "execution_class": case.execution_class,
        "protocol_status": protocol_status,
        "primary_capacity_eligible": primary_eligible,
        "full_completion_eligible": full_completion_eligible,
        "repeats_expected": case.repeats,
        "repeats_complete": len(runs),
        "speed_mps": case.speed_mps,
        "fault_line_ids": list(case.fault_line_ids),
        "seed_edges": [list(edge) for edge in case.seed_edges],
        "fault_schedule": case.fault_schedule,
        "status_echo_pass": status_echo_pass,
        "fixed_horizon_pass": fixed_horizon_pass,
        "cohort_pass": cohort_pass,
        "release_repeat_match": release_repeat_match,
        "comparison_eligible_by_repeat": run_values("comparison_eligible"),
        "released_segment_count_by_repeat": run_values("released_segment_count"),
        "planned_segment_count_by_repeat": run_values("planned_segment_count"),
        "completed_segment_count_by_repeat": run_values("completed_segment_count"),
        "canonical_complete_raw_bag_count_by_repeat": run_values(
            "canonical_complete_raw_bag_count"
        ),
        "canonical_success_rate_by_repeat": run_values("canonical_success_rate"),
        "wall_seconds_by_repeat": wall_seconds_by_repeat,
        "timing_scope": timing_scope,
        "secondary_timing_censored": timing_scope
        == "CENSORED_COMPLETED_SURVIVORS_SECONDARY",
        "processed_attempt_mean_minutes_by_repeat": (
            processed_attempt_means if full_completion_eligible else [None for _ in runs]
        ),
        "full_population_processed_attempt_minutes_by_repeat": (
            processed_attempt_distributions
            if full_completion_eligible
            else [None for _ in runs]
        ),
        "secondary_censored_processed_attempt_mean_minutes_by_repeat": (
            processed_attempt_means
            if timing_scope == "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
            else [None for _ in runs]
        ),
        "secondary_censored_processed_attempt_minutes_by_repeat": (
            processed_attempt_distributions
            if timing_scope == "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
            else [None for _ in runs]
        ),
    }


def aggregate_campaign(workload: Workload, output_root: Path) -> dict[str, Any]:
    root = _rooted(output_root).resolve()
    rows: list[dict[str, Any]] = []
    missing_primary: list[str] = []
    invalid_primary: list[str] = []

    for case in hca_cases():
        case_root = root / case.case_id
        expected_dirs = [case_root / f"run_{index:02d}" for index in range(1, case.repeats + 1)]
        complete_count = sum(g24._completed_run(run_dir) for run_dir in expected_dirs)
        if complete_count != case.repeats:
            status = (
                "ARCHIVED_ONLY_NOT_EXECUTED" if case.archived_only else "MISSING_OR_PARTIAL"
            )
            rows.append(
                {
                    "case_id": case.case_id,
                    "case_group": case.case_group,
                    "execution_class": case.execution_class,
                    "protocol_status": status,
                    "primary_capacity_eligible": False,
                    "repeats_expected": case.repeats,
                    "repeats_complete": complete_count,
                    "speed_mps": case.speed_mps,
                    "fault_line_ids": list(case.fault_line_ids),
                    "seed_edges": [list(edge) for edge in case.seed_edges],
                    "fault_schedule": case.fault_schedule,
                }
            )
            if not case.archived_only:
                missing_primary.append(case.case_id)
            continue
        row = _complete_case_row(case, workload, case_root)
        rows.append(row)
        if not case.archived_only and not row["primary_capacity_eligible"]:
            invalid_primary.append(case.case_id)

    primary_complete = sum(
        bool(row.get("primary_capacity_eligible")) for row in rows
    )
    status = (
        "COMPLETE_WITH_ARCHIVED_ONLY_GAP"
        if not missing_primary and not invalid_primary
        else "PARTIAL_OR_INVALID"
    )
    return {
        "schema": CAMPAIGN_SCHEMA,
        "status": status,
        "workload": {
            "manifest": _display_path(workload.manifest_path),
            "raw_input": _display_path(workload.raw_input),
            "canonical_input": _display_path(workload.canonical_input),
            "raw_task_count": workload.raw_task_count,
            "expanded_segment_count": workload.expanded_segment_count,
        },
        "protocol": {
            "start_epoch": START_EPOCH,
            "max_epochs": MAX_EPOCHS,
            "end_epoch": END_EPOCH,
            "cleanup_epoch_files": True,
            "expected_case_count": 20,
            "primary_case_count": 19,
            "archived_only_probe_case_ids": [
                case.case_id for case in hca_cases() if case.archived_only
            ],
            "fault_comparison_pairing": (
                "SAME_2X_CANONICAL_POPULATION_AND_FIXED_DENOMINATOR_NOT_"
                "PER_SEGMENT_FAULT_RELEASE_PAIRED"
            ),
        },
        "primary_complete_case_count": primary_complete,
        "missing_primary_case_ids": missing_primary,
        "invalid_primary_case_ids": invalid_primary,
        "rows": rows,
    }


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    import io

    stream = io.StringIO(newline="")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
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


def _add_workload_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--raw-input", type=Path, default=DEFAULT_RAW_INPUT)
    parser.add_argument("--canonical-input", type=Path, default=DEFAULT_CANONICAL_INPUT)
    parser.add_argument("--workload-manifest", type=Path, default=DEFAULT_WORKLOAD_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--map-path", type=Path, default=g24.DEFAULT_MAP)
    parser.add_argument("--classes-dir", type=Path, default=DEFAULT_CLASSES_DIR)
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--include-archived-probe", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    dry = commands.add_parser("dry-run", help="print all frozen Java commands")
    _add_workload_arguments(dry)
    _add_runtime_arguments(dry)
    dry.add_argument("--output-json", type=Path)

    case = commands.add_parser("case", help="run or resume one isolated HCA case")
    _add_workload_arguments(case)
    _add_runtime_arguments(case)
    case.add_argument("--case-id", required=True, choices=[c.case_id for c in hca_cases()])
    case.add_argument("--aggregate-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    case.add_argument("--aggregate-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)

    resume = commands.add_parser("resume", help="run missing primary cases in registry order")
    _add_workload_arguments(resume)
    _add_runtime_arguments(resume)
    resume.add_argument("--case-id", action="append", choices=[c.case_id for c in hca_cases()])
    resume.add_argument("--aggregate-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    resume.add_argument("--aggregate-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)

    aggregate = commands.add_parser("aggregate", help="aggregate existing case directories only")
    _add_workload_arguments(aggregate)
    aggregate.add_argument("--output-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    aggregate.add_argument("--output-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)
    return parser


def _workload_from_args(args: argparse.Namespace) -> Workload:
    return load_workload(args.raw_input, args.canonical_input, args.workload_manifest)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    workload = _workload_from_args(args)

    if args.command == "dry-run":
        value = dry_run_payload(args, workload)
        if args.output_json is not None:
            _write_json(args.output_json, value)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0

    if args.command == "aggregate":
        value = aggregate_campaign(workload, args.output_root)
        write_aggregate(value, args.output_json, args.output_csv)
        print(json.dumps({"status": value["status"], "primary_complete_case_count": value["primary_complete_case_count"]}))
        return 0 if value["status"] == "COMPLETE_WITH_ARCHIVED_ONLY_GAP" else 2

    if args.command == "case":
        status = run_case(args, workload, case_by_id(args.case_id))
        value = aggregate_campaign(workload, args.output_root)
        write_aggregate(value, args.aggregate_json, args.aggregate_csv)
        return status

    if args.command == "resume":
        selected = set(args.case_id or [])
        cases = [case for case in hca_cases() if not selected or case.case_id in selected]
        if not args.skip_compile:
            g24.compile_java(args.javac, _rooted(args.classes_dir))
        for case in cases:
            status = run_case(args, workload, case, skip_compile=True)
            if status != 0:
                return status
        value = aggregate_campaign(workload, args.output_root)
        write_aggregate(value, args.aggregate_json, args.aggregate_csv)
        return 0 if not value["invalid_primary_case_ids"] else 2

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (G29HcaError, g24.FreshHcaError) as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
