#!/usr/bin/env python3
"""Run the legacy Java HCA* baseline on the frozen G30 3x workload.

This is a deliberately thin orchestration layer.  G24 owns Java compilation,
execution, lifecycle alignment, and repeat resume; G26 owns the Chapter-5 case
registry; G29 owns the already-tested fixed-window HCA admission logic.  G30
only binds those pieces to the schedule-preserving 3x cohort and publishes a
portable campaign summary.  It does not implement or copy HCA*.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf24_fresh_hca as g24
from scripts.eval import run_g4irsf29_hca as g29


WORKLOAD_DIR = ROOT / "artifacts" / "tasks" / "g4irsf30"
DEFAULT_RAW_INPUT = WORKLOAD_DIR / "inputdata_flight_densified_3x.txt"
DEFAULT_CANONICAL_INPUT = WORKLOAD_DIR / "inputdata_flight_densified_3x.jsonl"
DEFAULT_WORKLOAD_MANIFEST = WORKLOAD_DIR / "g4irsf30_workload_manifest.json"
DEFAULT_CLASSES_DIR = ROOT / "build" / "g4irsf30_java"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "runtime" / "g4irsf30_hca"
DEFAULT_AGGREGATE_JSON = ROOT / "outputs" / "tables" / "g4irsf30_hca.json"
DEFAULT_AGGREGATE_CSV = ROOT / "outputs" / "tables" / "g4irsf30_hca.csv"

WORKLOAD_SCHEMA = "czr005.g4irsf30.workload_manifest.v1"
WORKLOAD_PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_3X"
CAMPAIGN_SCHEMA = "czr005.g4irsf30.hca_campaign.v1"
CASE_PROTOCOL_SCHEMA = "czr005.g4irsf30.hca_case_protocol.v1"

EXPECTED_RAW_TASKS = 85_518
EXPECTED_SEGMENTS = 130_809
EXPECTED_FLIGHTS = 1_080

# The formal window is inherited, not reinterpreted for the larger cohort.
START_EPOCH = g29.START_EPOCH
MAX_EPOCHS = g29.MAX_EPOCHS
END_EPOCH = g29.END_EPOCH
MAX_NEW_TASKS = g29.MAX_NEW_TASKS

Workload = g29.Workload
HcaCase = g29.HcaCase


class G30HcaError(RuntimeError):
    """Raised when the G30 workload or campaign contract is inconsistent."""


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def hca_cases() -> tuple[HcaCase, ...]:
    """Reuse the four-speed and sixteen-interruption G26/G29 registry."""

    return g29.hca_cases()


def case_by_id(case_id: str) -> HcaCase:
    try:
        return g29.case_by_id(case_id)
    except g29.G29HcaError as exc:
        raise G30HcaError(f"unknown G30 HCA case: {case_id}") from exc


def load_workload(
    raw_input: Path,
    canonical_input: Path,
    manifest_path: Path,
) -> Workload:
    """Admit exactly the generated schedule-preserving 3x cohort."""

    raw_path = _rooted(raw_input).resolve()
    canonical_path = _rooted(canonical_input).resolve()
    manifest_file = _rooted(manifest_path).resolve()
    for path in (raw_path, canonical_path, manifest_file):
        if not path.is_file():
            raise G30HcaError(f"missing G30 workload file: {path}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != WORKLOAD_SCHEMA
        or manifest.get("status") != "COMPLETE"
        or manifest.get("protocol") != WORKLOAD_PROTOCOL
    ):
        raise G30HcaError("G30 workload manifest is not the registered COMPLETE 3x cohort")

    raw_expected = int(manifest.get("raw_task_count", -1))
    segment_expected = int(manifest.get("expanded_segment_count", -1))
    flight_expected = int(manifest.get("flight_count", -1))
    if (
        raw_expected != EXPECTED_RAW_TASKS
        or segment_expected != EXPECTED_SEGMENTS
        or flight_expected != EXPECTED_FLIGHTS
    ):
        raise G30HcaError("G30 workload manifest does not contain the fixed 3x population")

    raw_lines = [
        line
        for line in raw_path.read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    ]
    raw_ids = [int(line.split()[0]) for line in raw_lines]
    if len(raw_lines) != raw_expected or len(set(raw_ids)) != raw_expected:
        raise G30HcaError("G30 raw row count or task_ID uniqueness does not match its manifest")

    canonical_count = 0
    canonical_task_ids: set[int] = set()
    with canonical_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            canonical_count += 1
            canonical_task_ids.add(int(row["task_id"]))
    if canonical_count != segment_expected or canonical_task_ids != set(raw_ids):
        raise G30HcaError("G30 canonical segments do not match the raw 3x bag cohort")

    return Workload(
        raw_input=raw_path,
        canonical_input=canonical_path,
        manifest_path=manifest_file,
        raw_task_count=raw_expected,
        expanded_segment_count=segment_expected,
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
    return g29._java_commands(
        case,
        workload=workload,
        map_path=map_path,
        classes_dir=classes_dir,
        output_root=output_root,
        java=java,
    )


def dry_run_payload(args: argparse.Namespace, workload: Workload) -> dict[str, Any]:
    """Describe all commands without compiling or starting a Java process."""

    value = g29.dry_run_payload(args, workload)
    value["schema"] = CAMPAIGN_SCHEMA
    for case in value["cases"]:
        if case["archived_only"] and not args.include_archived_probe:
            case["commands"] = []
            case["dry_run_execution_status"] = "ARCHIVED_ONLY_NOT_EXECUTED"
    value["workload"] = {
        "manifest": _display_path(workload.manifest_path),
        "raw_input": _display_path(workload.raw_input),
        "canonical_input": _display_path(workload.canonical_input),
        "protocol": WORKLOAD_PROTOCOL,
        "raw_task_count": workload.raw_task_count,
        "expanded_segment_count": workload.expanded_segment_count,
        "flight_count": int(workload.manifest["flight_count"]),
    }
    value["protocol"].update(
        {
            "workload_protocol": WORKLOAD_PROTOCOL,
            "fixed_raw_bag_denominator": workload.raw_task_count,
            "fixed_segment_population": workload.expanded_segment_count,
            "primary_process_run_count": 4 * 2 + 15,
            "fault_comparison_pairing": (
                "SAME_3X_CANONICAL_POPULATION_AND_FIXED_DENOMINATOR_NOT_"
                "PER_SEGMENT_FAULT_RELEASE_PAIRED"
            ),
        }
    )
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    g29._write_json(path, value)


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
                "protocol": WORKLOAD_PROTOCOL,
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
                else "G30_3X_PRIMARY_HCA_FIXED_POPULATION_CAPACITY"
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
    return g29._runner_namespace(
        args, workload, case, skip_compile=skip_compile
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


def _enrich_row(row: Mapping[str, Any], workload: Workload) -> dict[str, Any]:
    value = dict(row)
    value.update(
        {
            "fixed_raw_bag_denominator": workload.raw_task_count,
            "fixed_segment_population": workload.expanded_segment_count,
            "formal_timing_comparison_allowed": bool(
                row.get("full_completion_eligible") is True
            ),
            "survivor_timing_drives_verdict": False,
        }
    )
    return value


def _repeat_counts_consistent(row: Mapping[str, Any], repeats: int) -> bool:
    fields = (
        "released_segment_count_by_repeat",
        "planned_segment_count_by_repeat",
        "completed_segment_count_by_repeat",
        "canonical_complete_raw_bag_count_by_repeat",
    )
    for field in fields:
        values = row.get(field)
        if (
            not isinstance(values, list)
            or len(values) != repeats
            or any(not isinstance(value, int) for value in values)
            or len(set(values)) != 1
        ):
            return False
    return True


def _processed_attempt_distributions(
    case_root: Path,
    row: Mapping[str, Any],
    repeats: int,
) -> list[Mapping[str, Any] | None]:
    """Read the small metrics files already produced by the reused G24 parser."""

    values: list[Mapping[str, Any] | None] = []
    for index in range(1, repeats + 1):
        path = case_root / f"run_{index:02d}" / "metrics.json"
        if path.is_file():
            metrics = json.loads(path.read_text(encoding="utf-8"))
            distribution = (
                ((metrics.get("denominators") or {}).get("processed_attempt") or {}).get(
                    "minutes"
                )
            )
            values.append(dict(distribution) if isinstance(distribution, Mapping) else None)
            continue
        # Unit fixtures and old full-population aggregates may already expose it.
        fallback = row.get("full_population_processed_attempt_minutes_by_repeat")
        value = fallback[index - 1] if isinstance(fallback, list) and len(fallback) == repeats else None
        values.append(dict(value) if isinstance(value, Mapping) else None)
    return values


def _reinterpret_fixed_window_row(
    row: Mapping[str, Any],
    workload: Workload,
    case: HcaCase,
    case_root: Path,
) -> dict[str, Any]:
    """Apply G30's end-to-end fixed-window capacity admission.

    Unlike G29's exact-release race, 3x capacity is measured at the registered
    terminal epoch even when the legacy source has not released every segment.
    Release-trace equality remains a diagnostic and never substitutes for the
    fixed 85,518-bag denominator.
    """

    value = dict(row)
    complete_case = (
        value.get("status_echo_pass") is True
        and value.get("fixed_horizon_pass") is True
        and value.get("cohort_pass") is True
        and value.get("repeats_complete") == case.repeats
    )
    counts_consistent = complete_case and _repeat_counts_consistent(
        value, case.repeats
    )
    released = value.get("released_segment_count_by_repeat") or []
    planned = value.get("planned_segment_count_by_repeat") or []
    completed = value.get("completed_segment_count_by_repeat") or []
    raw_complete = value.get("canonical_complete_raw_bag_count_by_repeat") or []
    full_release = counts_consistent and all(
        count == workload.expanded_segment_count for count in released
    )
    full_plan = counts_consistent and all(
        count == workload.expanded_segment_count for count in planned
    )
    full_segment_completion = counts_consistent and all(
        count == workload.expanded_segment_count for count in completed
    )
    full_raw_completion = counts_consistent and all(
        count == workload.raw_task_count for count in raw_complete
    )
    full_completion = bool(
        not case.archived_only
        and case.case_group == "stable_speed"
        and full_release
        and full_plan
        and full_segment_completion
        and full_raw_completion
        and all(value is True for value in value.get("comparison_eligible_by_repeat", []))
    )
    case_protocol_pass = bool(
        case.case_group == "stable_speed"
        or value.get("primary_capacity_eligible") is True
    )
    primary_capacity = bool(
        not case.archived_only and counts_consistent and case_protocol_pass
    )
    distributions = _processed_attempt_distributions(
        case_root, value, case.repeats
    )
    means = [
        distribution.get("mean") if isinstance(distribution, Mapping) else None
        for distribution in distributions
    ]

    common_release = bool(
        counts_consistent and value.get("release_repeat_match") is True
    )
    common_release_count = released[0] if common_release and released else None
    stable_survivor_secondary = bool(
        case.case_group == "stable_speed" and primary_capacity and not full_completion
    )
    value.update(
        {
            "protocol_status": (
                "ARCHIVED_ONLY_PROBE_COMPLETE"
                if case.archived_only and complete_case
                else "EXACT_FULL_COMPLETION"
                if full_completion
                else "FIXED_HORIZON_END_TO_END_CAPACITY"
                if primary_capacity
                else "INVALID_OR_PARTIAL"
            ),
            "primary_capacity_eligible": primary_capacity,
            "counts_consistent_across_repeats": counts_consistent,
            "full_release_observed": full_release,
            "full_plan_observed": full_plan,
            "full_segment_completion_observed": full_segment_completion,
            "full_raw_bag_completion_observed": full_raw_completion,
            "full_completion_eligible": full_completion,
            "common_release_cohort_observed": common_release,
            "common_release_segment_count": common_release_count,
            "common_release_cohort_drives_capacity_verdict": False,
            "timing_scope": (
                "FULL_POPULATION"
                if full_completion
                else "CAPACITY_ONLY_TABLE_5_5"
                if case.case_group == "all_day_line_interruption" and primary_capacity
                else "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
                if stable_survivor_secondary
                else "NOT_ADMITTED"
            ),
            "secondary_timing_censored": stable_survivor_secondary,
            "processed_attempt_mean_minutes_by_repeat": (
                means if full_completion else [None for _ in distributions]
            ),
            "full_population_processed_attempt_minutes_by_repeat": (
                distributions
                if full_completion
                else [None for _ in distributions]
            ),
            "secondary_censored_processed_attempt_mean_minutes_by_repeat": (
                means
                if stable_survivor_secondary
                else [None for _ in distributions]
            ),
            "secondary_censored_processed_attempt_minutes_by_repeat": (
                distributions
                if stable_survivor_secondary
                else [None for _ in distributions]
            ),
        }
    )
    return _enrich_row(value, workload)


def _complete_case_row(
    case: HcaCase, workload: Workload, case_root: Path
) -> dict[str, Any]:
    """Reuse G29 parsing, then apply the registered G30 capacity semantics."""

    base = g29._complete_case_row(case, workload, case_root)
    return _reinterpret_fixed_window_row(base, workload, case, case_root)


def aggregate_campaign(workload: Workload, output_root: Path) -> dict[str, Any]:
    """Relabel the tested G29 aggregate contract for the frozen 3x cohort."""

    root = _rooted(output_root).resolve()
    base = g29.aggregate_campaign(workload, root)
    value = dict(base)
    value["schema"] = CAMPAIGN_SCHEMA
    value["workload"] = {
        **dict(base["workload"]),
        "protocol": WORKLOAD_PROTOCOL,
        "flight_count": int(workload.manifest["flight_count"]),
    }
    value["protocol"] = {
        **dict(base["protocol"]),
        "workload_protocol": WORKLOAD_PROTOCOL,
        "fixed_raw_bag_denominator": workload.raw_task_count,
        "fixed_segment_population": workload.expanded_segment_count,
        "primary_process_run_count": 4 * 2 + 15,
        "fault_comparison_pairing": (
            "SAME_3X_CANONICAL_POPULATION_AND_FIXED_DENOMINATOR_NOT_"
            "PER_SEGMENT_FAULT_RELEASE_PAIRED"
        ),
        "timing_claim": "FULL_POPULATION_ONLY",
        "partial_release_claim": "FIXED_HORIZON_END_TO_END_CAPACITY",
        "stable_capacity_admission": (
            "TWO_COMPLETE_FIXED_WINDOW_REPEATS_WITH_MATCHING_COUNTS_ON_THE_"
            "CANONICAL_POPULATION;_FULL_RELEASE_NOT_REQUIRED"
        ),
    }
    cases = {case.case_id: case for case in hca_cases()}
    value["rows"] = [
        _reinterpret_fixed_window_row(
            row, workload, cases[str(row["case_id"])], root / str(row["case_id"])
        )
        if "status_echo_pass" in row
        else _enrich_row(row, workload)
        for row in base["rows"]
    ]
    invalid = sorted(
        str(row["case_id"])
        for row in value["rows"]
        if row.get("execution_class") != "ARCHIVED_ONLY_PROBE"
        and row.get("repeats_complete") == row.get("repeats_expected")
        and row.get("primary_capacity_eligible") is not True
    )
    value["invalid_primary_case_ids"] = invalid
    value["primary_complete_case_count"] = sum(
        row.get("primary_capacity_eligible") is True for row in value["rows"]
    )
    value["status"] = (
        "COMPLETE_WITH_ARCHIVED_ONLY_GAP"
        if not value["missing_primary_case_ids"] and not invalid
        else "PARTIAL_OR_INVALID"
    )
    return value


def write_aggregate(
    value: Mapping[str, Any], json_path: Path, csv_path: Path
) -> None:
    g29.write_aggregate(value, json_path, csv_path)


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
        selected_primary = {
            case.case_id for case in cases if not case.archived_only
        }
        blocked = selected_primary.intersection(
            set(value["missing_primary_case_ids"])
            | set(value["invalid_primary_case_ids"])
        )
        return 0 if not blocked else 2

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (G30HcaError, g24.FreshHcaError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
