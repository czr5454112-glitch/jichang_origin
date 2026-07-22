"""Run exact rolling-continuity and 8x/16x G4IRSF11 stress extensions."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.eval.g4irsf11_evaluation_reporting import case_row, sha256_file, write_csv  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    CANONICAL_MAP_SHA256,
    assert_canonical_map,
    canonical_map_identity,
)
from scripts.eval.g4irsf11_experiment_protocol import (  # noqa: E402
    EXTENSION_PROTOCOL_VERSION,
    system_extension_cases,
    system_extension_manifest,
)
from scripts.eval.g4irsf11_workloads import load_jsonl  # noqa: E402
from scripts.eval.g4irsf11_result_validation import (  # noqa: E402
    atomic_write_text,
    canonical_manifest_sha256,
    read_json_object,
)
from scripts.eval.g4irsf11_publication import (  # noqa: E402
    artifact_bindings as publication_artifact_bindings,
    begin_completion,
    complete_publication,
    completion_validation_errors,
    create_staging_root,
    promote_staged_artifacts,
    semantic_file_sha256,
)
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (  # noqa: E402
    MAP_PATH,
    SOURCE_TASK_PATH,
    _case_paths,
    _canonical_case_inputs,
    _descriptor_matches,
    _fixed_map_protocol_manifest,
    _acquire_case_lock,
    _acquire_all_case_locks,
    assert_implementation_unchanged,
    _release_case_lock,
    _read_json,
    _write_json,
    execute_case,
    assert_frozen_inputs_unchanged,
    implementation_sha256,
    implementation_source_sha256,
    load_source_task_snapshot,
    source_task_identity,
)


PROTOCOL_PATH = ROOT / "artifacts" / "gates" / "g4irsf11_system_extension_protocol.json"
EXTENSION_COMPLETION_PATH = (
    ROOT / "artifacts" / "gates" / "g4irsf11_system_extension_completion.json"
)
TABLE_PATH = ROOT / "outputs" / "tables" / "g4irsf11_system_extension_matrix.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "g4irsf11_system_extension_report.md"
EXTENSION_PUBLICATION_ARTIFACTS = (
    "artifacts/gates/g4irsf11_system_extension_protocol.json",
    "outputs/tables/g4irsf11_system_extension_matrix.csv",
    "outputs/reports/g4irsf11_system_extension_report.md",
)
PROTOCOL_LOCK = ROOT / ".pytest_cache" / "g4irsf11" / "event_evaluation" / "system_extension_protocol.lock"
CONSOLIDATION_LOCK = (
    ROOT
    / ".pytest_cache"
    / "g4irsf11"
    / "event_evaluation"
    / "system_extension_consolidation.lock"
)


def extension_protocol_manifest() -> dict[str, Any]:
    """Return the fixed-map-bound, checkout-independent extension protocol."""

    return _fixed_map_protocol_manifest(system_extension_manifest(), extension=True)


def _extension_case_set_sha256() -> str:
    return canonical_manifest_sha256(
        {"case_ids": [case.case_id for case in system_extension_cases()]}
    )


def _extension_producer(
    args: argparse.Namespace,
    *,
    implementation_digest: str,
    frozen_source_identity: Mapping[str, Any] | None = None,
    frozen_map_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_identity_value = dict(frozen_source_identity or source_task_identity())
    map_identity_value = dict(frozen_map_identity or canonical_map_identity())
    return {
        "schema": "czr005.g4irsf11.evidence_producer.v1",
        "scope": "system_extension",
        "protocol_version": EXTENSION_PROTOCOL_VERSION,
        "protocol_manifest_sha256": canonical_manifest_sha256(
            extension_protocol_manifest()
        ),
        "fixed_real_map_only": True,
        "canonical_map_path": map_identity_value["repo_relative_path"],
        "canonical_map_sha256": map_identity_value["sha256"],
        "canonical_map_raw_bytes_sha256": map_identity_value["raw_bytes_sha256"],
        "topology_mutation_allowed": map_identity_value["topology_mutation_allowed"],
        "source_task_path": source_identity_value["path"],
        "source_task_raw_bytes_sha256": source_identity_value["raw_bytes_sha256"],
        "source_task_semantic_sha256": source_identity_value["semantic_sha256"],
        "source_task_row_count": source_identity_value["row_count"],
        "implementation_sha256": implementation_digest,
        "implementation_source_bundle_sha256": implementation_source_sha256(),
        "measurement_cohort": {
            "name": str(args.measurement_cohort),
            "declared_concurrent_worker_target": int(args.concurrent_worker_target),
        },
        "extension_case_set_sha256": _extension_case_set_sha256(),
        "expected_case_count": len(system_extension_cases()),
    }


def _extension_completion_metadata(
    args: argparse.Namespace,
    *,
    implementation_digest: str,
    executed_case_count: int,
    no_smoke_substitution_pass: bool,
    frozen_source_identity: Mapping[str, Any] | None = None,
    frozen_map_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_identity_value = dict(frozen_source_identity or source_task_identity())
    map_identity_value = dict(frozen_map_identity or canonical_map_identity())
    producer = _extension_producer(
        args,
        implementation_digest=implementation_digest,
        frozen_source_identity=source_identity_value,
        frozen_map_identity=map_identity_value,
    )
    return {
        "scope": "system_extension",
        "protocol_version": EXTENSION_PROTOCOL_VERSION,
        "protocol_manifest_sha256": canonical_manifest_sha256(
            extension_protocol_manifest()
        ),
        "fixed_real_map_only": True,
        "canonical_map_sha256": map_identity_value["sha256"],
        "canonical_map_path": map_identity_value["repo_relative_path"],
        "canonical_map_raw_bytes_sha256": map_identity_value["raw_bytes_sha256"],
        "topology_mutation_allowed": map_identity_value["topology_mutation_allowed"],
        "source_task_path": source_identity_value["path"],
        "source_task_raw_bytes_sha256": source_identity_value["raw_bytes_sha256"],
        "source_task_semantic_sha256": source_identity_value["semantic_sha256"],
        "source_task_row_count": source_identity_value["row_count"],
        "implementation_sha256": implementation_digest,
        "implementation_source_bundle_sha256": implementation_source_sha256(),
        "measurement_cohort": producer["measurement_cohort"],
        "concurrent_worker_target": int(args.concurrent_worker_target),
        "expected_case_count": len(system_extension_cases()),
        "executed_case_count": int(executed_case_count),
        "extension_case_set_sha256": _extension_case_set_sha256(),
        "no_smoke_substitution_pass": bool(no_smoke_substitution_pass),
        "producer": producer,
        "producer_sha256": canonical_manifest_sha256(producer),
    }


def extension_completion_validation_errors(root: Path = ROOT) -> list[str]:
    current_source_identity = source_task_identity()
    current_map_identity = canonical_map_identity()
    expected_metadata = {
        "protocol_version": EXTENSION_PROTOCOL_VERSION,
        "fixed_real_map_only": True,
        "canonical_map_sha256": current_map_identity["sha256"],
        "canonical_map_path": current_map_identity["repo_relative_path"],
        "topology_mutation_allowed": current_map_identity["topology_mutation_allowed"],
        "source_task_path": current_source_identity["path"],
        "source_task_semantic_sha256": current_source_identity["semantic_sha256"],
        "source_task_row_count": current_source_identity["row_count"],
        "expected_case_count": len(system_extension_cases()),
        "executed_case_count": len(system_extension_cases()),
        "extension_case_set_sha256": _extension_case_set_sha256(),
        "no_smoke_substitution_pass": True,
    }
    completion_path = root / EXTENSION_COMPLETION_PATH.relative_to(ROOT)
    errors = completion_validation_errors(
        root,
        completion_path,
        expected_scope="system_extension",
        expected_source_bundle_sha256=implementation_source_sha256(),
        expected_protocol_manifest_sha256=canonical_manifest_sha256(
            extension_protocol_manifest()
        ),
        expected_artifact_paths=EXTENSION_PUBLICATION_ARTIFACTS,
        expected_metadata=expected_metadata,
    )
    protocol_path = root / PROTOCOL_PATH.relative_to(ROOT)
    try:
        published_protocol = read_json_object(protocol_path)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        errors.append(
            f"published extension protocol cannot be decoded: {type(exc).__name__}: {exc}"
        )
    else:
        if published_protocol != extension_protocol_manifest():
            errors.append("published extension protocol differs from the exact protocol")
    if completion_path.is_file():
        try:
            completion = read_json_object(completion_path)
        except (OSError, TypeError, ValueError):
            completion = {}
        runtime_digest = str(completion.get("implementation_sha256") or "")
        if len(runtime_digest) != 64 or any(
            character not in "0123456789abcdef" for character in runtime_digest
        ):
            errors.append("extension completion runtime implementation SHA-256 is invalid")
        for raw_key in (
            "canonical_map_raw_bytes_sha256",
            "source_task_raw_bytes_sha256",
        ):
            raw_digest = str(completion.get(raw_key) or "")
            if len(raw_digest) != 64 or any(
                character not in "0123456789abcdef" for character in raw_digest
            ):
                errors.append(f"extension completion {raw_key} is invalid")
        producer = (
            completion.get("producer")
            if isinstance(completion.get("producer"), Mapping)
            else {}
        )
        if producer.get("scope") != "system_extension":
            errors.append("extension completion producer scope is unexpected")
        if completion.get("producer_sha256") != canonical_manifest_sha256(producer):
            errors.append("extension completion producer SHA-256 binding differs")
        for key in (
            "protocol_version",
            "protocol_manifest_sha256",
            "fixed_real_map_only",
            "canonical_map_path",
            "canonical_map_sha256",
            "canonical_map_raw_bytes_sha256",
            "topology_mutation_allowed",
            "source_task_path",
            "source_task_raw_bytes_sha256",
            "source_task_semantic_sha256",
            "source_task_row_count",
            "implementation_sha256",
            "implementation_source_bundle_sha256",
            "measurement_cohort",
            "extension_case_set_sha256",
            "expected_case_count",
        ):
            if producer.get(key) != completion.get(key):
                errors.append(f"extension completion producer field differs: {key}")
        cohort = completion.get("measurement_cohort")
        if not isinstance(cohort, Mapping) or not str(cohort.get("name") or "").strip():
            errors.append("extension completion measurement cohort is empty")
        try:
            worker_target = int(
                cohort.get("declared_concurrent_worker_target")
                if isinstance(cohort, Mapping)
                else 0
            )
        except (TypeError, ValueError):
            worker_target = 0
        if worker_target <= 0:
            errors.append("extension completion concurrent worker target is invalid")
        if completion.get("concurrent_worker_target") != worker_target:
            errors.append("extension top-level worker target differs from cohort")
    return errors


def _continuity_audit(
    row: Mapping[str, Any], *, workload_rows: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    item = dict(row)
    expected = {
        "extension_rolling_2day_full": 87_206,
        "extension_rolling_7day_full": 305_221,
        "extension_synchronized_8x_full": 348_824,
        "extension_synchronized_16x_full": 697_648,
        "extension_fault_delayed_16x_full": 697_648,
    }.get(str(row.get("case_id")))
    actual = int(float(row.get("workload_segment_count") or 0))
    item["expected_exact_segment_count"] = expected if expected is not None else ""
    item["exact_segment_count_pass"] = expected is not None and actual == expected
    release_min = float("inf")
    release_max = float("-inf")
    for workload_row in workload_rows:
        release = float(workload_row["release_time"])
        release_min = min(release_min, release)
        release_max = max(release_max, release)
    span = (
        release_max - release_min
        if workload_rows
        else float(row.get("arrival_span_seconds") or 0.0)
    )
    item["arrival_span_seconds"] = span
    item["retained_workload_row_count"] = len(workload_rows)
    item["retained_workload_count_pass"] = bool(workload_rows) and len(workload_rows) == actual
    required_boundaries = 6 if row.get("case_id") == "extension_rolling_7day_full" else (
        1 if row.get("case_id") == "extension_rolling_2day_full" else 0
    )
    item["required_day_boundaries"] = required_boundaries
    item["observed_full_day_boundaries"] = int(span // 86_400.0)
    item["day_boundary_pass"] = (
        int(span // 86_400.0) >= required_boundaries if required_boundaries else True
    )
    expected_copies = 7 if row.get("case_id") == "extension_rolling_7day_full" else (
        2 if row.get("case_id") == "extension_rolling_2day_full" else 0
    )
    is_rolling = expected_copies > 0
    coverage_sha256 = str(row.get("continuity_input_coverage_sha256") or "")
    coverage_digest_valid = (
        len(coverage_sha256) == 64
        and all(character in "0123456789abcdef" for character in coverage_sha256)
    )
    item["continuity_evidence_required"] = is_rolling
    item["continuity_evidence_pass"] = (
        row.get("continuity_status") == "PASS"
        and row.get("continuity_single_runtime_invocation_pass") is True
        and str(row.get("continuity_runtime_instance_id") or "")
        == str(row.get("run_id") or "")
        and bool(str(row.get("run_id") or ""))
        and int(row.get("continuity_boundary_count") or -1) == expected_copies - 1
        and row.get("continuity_input_audit_status") == "PASS"
        and int(row.get("continuity_input_expected_copy_count") or -1) == expected_copies
        and int(row.get("continuity_input_workload_row_count") or -1) == actual
        and int(row.get("continuity_input_base_segment_count") or -1) > 0
        and coverage_digest_valid
        and not str(row.get("continuity_blockers") or "")
    ) if is_rolling else ""
    item["carry_over_observed"] = (
        row.get("continuity_carry_over_observed") is True if is_rolling else ""
    )
    item["no_smoke_substitution_pass"] = (
        row.get("execution_status") == "EXECUTED"
        and bool(item["exact_segment_count_pass"])
        and bool(item["retained_workload_count_pass"])
        and bool(item["day_boundary_pass"])
        and (not is_rolling or item["continuity_evidence_pass"] is True)
    )
    return item


def _load_rows(
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
    expected_args: argparse.Namespace | None = None,
    base_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if expected_args is not None and base_rows is None:
        raise ValueError(
            "extension consolidation requires current source rows for canonical input rebuild"
        )
    rows: list[dict[str, Any]] = []
    for case in system_extension_cases():
        paths = _case_paths(case)
        execution: dict[str, Any] = {
            "status": "NOT_RUN",
            "blocker": "exact system extension case not executed",
        }
        result = None
        expected_workload_rows: list[dict[str, Any]] | None = None
        expected_fault_rows: list[dict[str, Any]] | None = None
        canonical_inputs_valid = True
        if expected_args is not None:
            try:
                expected_workload_rows, expected_fault_rows = _canonical_case_inputs(
                    case, base_rows or []
                )
            except (KeyError, TypeError, ValueError) as exc:
                canonical_inputs_valid = False
                execution = {
                    "status": "FAILED",
                    "return_code": "CANONICAL_INPUT_REBUILD_ERROR",
                    "blocker": (
                        "current source rows could not rebuild the extension workload/fault "
                        f"for consolidation ({type(exc).__name__}: {exc})"
                    ),
                }
        if canonical_inputs_valid and paths["execution"].is_file():
            try:
                candidate = _read_json(paths["execution"])
            except (OSError, TypeError, ValueError) as exc:
                execution = {
                    "status": "FAILED",
                    "return_code": "DESCRIPTOR_DECODE_ERROR",
                    "blocker": (
                        "extension execution descriptor could not be decoded; the case "
                        f"evidence is not consolidatable ({type(exc).__name__})"
                    ),
                }
            else:
                if _descriptor_matches(
                    candidate,
                    case,
                    source_sha256=source_sha256,
                    map_sha256=map_sha256,
                    implementation_digest=implementation_digest,
                    protocol_version=EXTENSION_PROTOCOL_VERSION,
                    expected_args=expected_args,
                    expected_workload_rows=expected_workload_rows,
                    expected_fault_rows=expected_fault_rows,
                ):
                    execution = candidate
                    try:
                        result = _read_json(paths["result"])
                    except (OSError, TypeError, ValueError) as exc:
                        execution = dict(candidate)
                        execution["claimed_execution_status"] = "EXECUTED"
                        execution["status"] = "FAILED"
                        execution["return_code"] = "RESULT_DECODE_ERROR"
                        execution["blocker"] = (
                            "validated extension result could not be decoded during "
                            f"consolidation ({type(exc).__name__})"
                        )
                elif candidate.get("status") == "RUNNING":
                    execution = dict(candidate)
                    execution["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
                    execution["blocker"] = (
                        "stale/unverified extension RUNNING descriptor is not reusable; "
                        "archive it explicitly and rerun"
                    )
                elif candidate.get("status") == "EXECUTED":
                    execution = dict(candidate)
                    execution["claimed_execution_status"] = "EXECUTED"
                    execution["status"] = "FAILED"
                    execution["blocker"] = (
                        "extension descriptor claimed EXECUTED but strict identity/artifact/"
                        "semantic bundle validation failed; result is not reportable as executed"
                    )
                else:
                    execution = candidate
        workload_rows: list[dict[str, Any]] = []
        if paths["workload"].is_file():
            try:
                candidate_workload_rows = load_jsonl(paths["workload"])
                for index, workload_row in enumerate(candidate_workload_rows):
                    release_time = float(workload_row["release_time"])
                    if not math.isfinite(release_time):
                        raise ValueError(
                            f"workload row {index} release_time must be finite"
                        )
                workload_rows = candidate_workload_rows
            except (KeyError, OSError, TypeError, ValueError) as exc:
                prior_blocker = str(execution.get("blocker") or "")
                execution = dict(execution)
                if execution.get("status") == "EXECUTED":
                    execution["claimed_execution_status"] = "EXECUTED"
                execution["status"] = "FAILED"
                execution["return_code"] = "WORKLOAD_DECODE_ERROR"
                workload_blocker = (
                    "retained extension workload could not be decoded and semantically "
                    f"validated ({type(exc).__name__})"
                )
                execution["blocker"] = "; ".join(
                    blocker for blocker in (prior_blocker, workload_blocker) if blocker
                )
        rows.append(
            _continuity_audit(
                case_row(case, result, execution),
                workload_rows=workload_rows,
            )
        )
    return rows


def _write_report(
    rows: Sequence[Mapping[str, Any]], *, report_path: Path = REPORT_PATH
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4IRSF11 Exact Continuity and Extreme-Stress Extensions",
        "",
        "These cases supplement the frozen 84-case matrix. They do not replace it and use no first-N segment limit.",
        "",
        "| Case | Execution | Exact input | Continuity evidence | Carry-over observed | Day boundary | Completed / requested | Capacity | Blocker |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        completed = f"{row.get('completed_segment_count', 0)} / {row.get('workload_segment_count', 0)}"
        lines.append(
            "| {case_id} | {execution_status} | {exact_segment_count_pass} | "
            "{continuity_evidence_pass} | {carry_over_observed} | {day_boundary_pass} | "
            "{completed} | {capacity_pass} | {blocker} |".format(
                completed=completed,
                **row,
            )
        )
    lines.extend(
        [
            "",
            "Safe execution and capacity are independent. An 8x/16x run is never promoted merely because it avoids conflicts.",
            "For rolling cases, carry-over is reported as an observed fact separate from continuity validity; a false value is never described as observed carry-over.",
            "",
        ]
    )
    atomic_write_text(report_path, "\n".join(lines))


def _consolidation_complete(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Require every frozen extension bundle and its exact-input audit."""

    return bool(rows) and all(
        row.get("execution_status") == "EXECUTED"
        and row.get("no_smoke_substitution_pass") is True
        for row in rows
    )


def _extension_stage_validation_errors(
    rows: Sequence[Mapping[str, Any]],
    *,
    args: argparse.Namespace,
    implementation_digest: str,
) -> list[str]:
    errors: list[str] = []
    expected_ids = [case.case_id for case in system_extension_cases()]
    actual_ids = [str(row.get("case_id") or "") for row in rows]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(actual_ids):
        errors.append("extension staged ledger case set/order is not exact")
    protocol_digest = canonical_manifest_sha256(extension_protocol_manifest())
    for row in rows:
        case_id = str(row.get("case_id") or "<missing>")
        if row.get("execution_status") != "EXECUTED":
            errors.append(f"extension staged case is not EXECUTED: {case_id}")
        if row.get("no_smoke_substitution_pass") is not True:
            errors.append(f"extension staged case exact-input audit failed: {case_id}")
        if row.get("protocol_manifest_sha256") != protocol_digest:
            errors.append(f"extension staged case protocol differs: {case_id}")
        if row.get("map_sha256") != CANONICAL_MAP_SHA256:
            errors.append(f"extension staged case map differs: {case_id}")
        if row.get("implementation_sha256") != implementation_digest:
            errors.append(f"extension staged case implementation differs: {case_id}")
        if row.get("measurement_cohort") != str(args.measurement_cohort):
            errors.append(f"extension staged case cohort differs: {case_id}")
        if row.get("declared_concurrent_worker_target") != int(
            args.concurrent_worker_target
        ):
            errors.append(f"extension staged case worker target differs: {case_id}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Exact extension case ID; repeatable")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--keep-workloads",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Retain ignored exact inputs so full row counts and day boundaries can be re-audited.",
    )
    parser.add_argument("--execute-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=14_400.0)
    parser.add_argument("--max-events", type=int, default=50_000_000)
    parser.add_argument("--measurement-cohort", required=True)
    parser.add_argument("--concurrent-worker-target", type=int, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--search-path", type=Path, default=ROOT / "build_vs" / "python" / "Release")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.keep_workloads:
        raise SystemExit(
            "strict extension v2 forbids --no-keep-workloads because consolidation "
            "must rebuild and rehash exact inputs"
        )
    if args.concurrent_worker_target <= 0:
        raise SystemExit("--concurrent-worker-target must be positive")
    if not args.measurement_cohort.strip():
        raise SystemExit("--measurement-cohort must be non-empty")
    cases = system_extension_cases()
    by_id = {case.case_id: case for case in cases}
    if args.case:
        unknown = sorted(set(args.case) - set(by_id))
        if unknown:
            raise SystemExit(f"unknown --case values: {unknown}")
        selected = [by_id[name] for name in args.case]
    else:
        selected = list(cases)

    assert_canonical_map(MAP_PATH)
    frozen_map_identity = canonical_map_identity()
    manifest = extension_protocol_manifest()
    base_rows, frozen_source_identity = load_source_task_snapshot()
    if len(base_rows) != 43_603:
        raise SystemExit(f"formal source task count must be 43603, got {len(base_rows)}")
    source_sha256 = str(frozen_source_identity["raw_bytes_sha256"])
    map_sha256 = CANONICAL_MAP_SHA256
    implementation_digest = implementation_sha256(args.search_path)

    def assert_measurement_identity_unchanged() -> None:
        assert_implementation_unchanged(implementation_digest, args.search_path)
        assert_frozen_inputs_unchanged(
            frozen_source_identity, frozen_map_identity
        )

    assert_measurement_identity_unchanged()
    failures = 0
    for index, case in enumerate(selected, start=1):
        assert_measurement_identity_unchanged()
        print(f"[g4irsf11-extension] {index}/{len(selected)} START {case.case_id}", flush=True)
        _, execution = execute_case(
            case,
            base_rows,
            args,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            protocol_version=EXTENSION_PROTOCOL_VERSION,
            protocol_manifest_value=manifest,
        )
        assert_measurement_identity_unchanged()
        failures += execution.get("status") != "EXECUTED"
        print(
            f"[g4irsf11-extension] {index}/{len(selected)} {execution.get('status')} {case.case_id}",
            flush=True,
        )
    if args.execute_only:
        assert_measurement_identity_unchanged()
        return 2 if failures else 0
    consolidation_lock = _acquire_case_lock(
        CONSOLIDATION_LOCK,
        "system_extension_consolidation",
        wait_seconds=60.0,
    )
    if consolidation_lock is None:
        raise SystemExit(
            f"could not acquire system extension consolidation lock {CONSOLIDATION_LOCK}"
        )
    case_snapshot_locks: list[dict[str, Any]] = []
    stage_errors: list[str] = []
    try:
        acquired_case_locks = _acquire_all_case_locks(
            cases,
            scope="extension_consolidation_snapshot",
            wait_seconds=60.0,
        )
        if acquired_case_locks is None:
            raise SystemExit(
                "could not acquire every extension case lock within 60 seconds; "
                "no staged or published extension report was rewritten"
            )
        case_snapshot_locks = acquired_case_locks
        stage_root = create_staging_root(ROOT, "system_extension")
        assert_measurement_identity_unchanged()
        _write_json(stage_root / PROTOCOL_PATH.relative_to(ROOT), manifest)
        rows = _load_rows(
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            expected_args=args,
            base_rows=base_rows,
        )
        write_csv(stage_root / TABLE_PATH.relative_to(ROOT), rows)
        _write_report(
            rows, report_path=stage_root / REPORT_PATH.relative_to(ROOT)
        )
        assert_measurement_identity_unchanged()
        stage_errors.extend(
            _extension_stage_validation_errors(
                rows,
                args=args,
                implementation_digest=implementation_digest,
            )
        )
        try:
            staged_bindings = publication_artifact_bindings(
                stage_root, EXTENSION_PUBLICATION_ARTIFACTS
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            stage_errors.append(
                "extension staged publication binding failed: "
                f"{type(exc).__name__}: {exc}"
            )
            staged_bindings = {}
        executed_case_count = sum(
            row["execution_status"] == "EXECUTED" for row in rows
        )
        complete = (
            not failures
            and not stage_errors
            and _consolidation_complete(rows)
            and executed_case_count == len(rows) == len(cases)
        )
        final_metadata = _extension_completion_metadata(
            args,
            implementation_digest=implementation_digest,
            executed_case_count=executed_case_count,
            no_smoke_substitution_pass=complete,
            frozen_source_identity=frozen_source_identity,
            frozen_map_identity=frozen_map_identity,
        )
        if complete:
            assert_measurement_identity_unchanged()
            transaction = begin_completion(
                EXTENSION_COMPLETION_PATH,
                final_metadata,
                expected_bindings=staged_bindings,
            )
            promote_staged_artifacts(
                stage_root,
                ROOT,
                EXTENSION_PUBLICATION_ARTIFACTS,
                staged_bindings,
            )
            assert_measurement_identity_unchanged()
            complete_publication(
                EXTENSION_COMPLETION_PATH,
                final_metadata,
                root=ROOT,
                artifact_paths=EXTENSION_PUBLICATION_ARTIFACTS,
                expected_bindings=staged_bindings,
                publication_id=str(transaction["publication_id"]),
            )
            try:
                assert_measurement_identity_unchanged()
            except Exception:
                begin_completion(
                    EXTENSION_COMPLETION_PATH,
                    final_metadata,
                    expected_bindings=staged_bindings,
                )
                raise
    finally:
        for case_lock in reversed(case_snapshot_locks):
            _release_case_lock(case_lock)
        _release_case_lock(consolidation_lock)
    print(
        json.dumps(
            {
                "executed": sum(row["execution_status"] == "EXECUTED" for row in rows),
                "case_count": len(rows),
                "exact_inputs": sum(bool(row["no_smoke_substitution_pass"]) for row in rows),
                "failures": failures,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    for blocker in stage_errors:
        print(f"[g4irsf11-extension] publication blocker: {blocker}", flush=True)
    return 2 if failures or not complete else 0


if __name__ == "__main__":
    raise SystemExit(main())
