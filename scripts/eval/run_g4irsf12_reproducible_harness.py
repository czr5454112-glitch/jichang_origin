"""CLI for the fail-closed G4IRSF12 B/C/E/F/G/H/J experiment harness.

Without ``--execute`` this command only writes a complete NOT_RUN/PENDING
matrix plus parsed controls.  The default execution ceiling is 2,048
segments.  8,192 and full original-1x runs require separate explicit flags
and accepted prior evidence.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    CANONICAL_MAP_PATH,
    assert_canonical_map,
    canonical_graph_records,
)
from scripts.eval.g4irsf12_reproducible_harness import (  # noqa: E402
    FULL_SIZE_SEGMENTS,
    RESOURCE_LABELS,
    RESULT_SCHEMA,
    SIZE_LADDER,
    CaseSpec,
    all_cases,
    apply_repeat_consistency,
    authorization_blockers,
    execute_case,
    file_sha256,
    inspect_executor,
    load_control_evidence,
    load_result_ledger,
    planned_results,
    source_bundle_sha256,
    write_harness_outputs,
)


DEFAULT_SOURCE_PATHS = (
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("scripts/eval/run_g4irsf12_reproducible_harness.py"),
    Path("scripts/eval/g4irsf12_size_ladder.py"),
    Path("scripts/eval/g4irsf11_experiment_protocol.py"),
    Path("src/czr005/cpp_backend.py"),
    Path("src/czr005/datasets/decision_trace.py"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    Path("cpp/ics_core/runtime/expiring_first_edge_credit.hpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/graph/graph.hpp"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
)
ALL_PHASES = frozenset({"B", "C", "E", "F", "G", "H", "J"})
FROZEN_CONTROL_EVIDENCE_STATUSES = frozenset(
    {
        "PARSED_HISTORICAL_HCA_NOT_FRESH_RERUN",
        "PARSED_FROZEN_V2_SAFE_NOT_RERUN",
        "COMMITTED_G4IRSF11_NEGATIVE_CONTROL_NOT_RERUN",
    }
)


def _executor(value: str) -> Callable[..., Mapping[str, Any]]:
    module_name, separator, attribute = value.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("--executor must use module.path:function syntax")
    module = importlib.import_module(module_name)
    candidate = getattr(module, attribute)
    if not callable(candidate):
        raise TypeError(f"executor is not callable: {value}")
    return candidate


def _phases(value: str) -> set[str]:
    phases = {item.strip().upper() for item in value.split(",") if item.strip()}
    invalid = phases - ALL_PHASES
    if not phases or invalid:
        raise ValueError(f"invalid --phases value: {value}")
    return phases


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="invoke selected cases; omitted means plan-only NOT_RUN/PENDING output",
    )
    parser.add_argument(
        "--executor",
        default="czr005.cpp_backend:g4irsf11_event_runtime_from_records",
    )
    parser.add_argument(
        "--binary",
        type=Path,
        help="exact loaded runtime binary/artifact to hash; required with --execute",
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        help="optional C++ extension search path forwarded when supported",
    )
    parser.add_argument("--phases", default="B,C,E,F,G,H,J")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="execute only this case ID; repeatable",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        choices=SIZE_LADDER,
        default=2_048,
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--allow-8192", action="store_true")
    parser.add_argument("--allow-full", action="store_true")
    parser.add_argument(
        "--promoted-resource",
        action="append",
        default=[],
        help="R0-R4 resource label selected for the best-two 8192 review; repeatable",
    )
    parser.add_argument(
        "--promoted-finalist",
        action="append",
        default=[],
        help="candidate ID explicitly promoted to J; repeatable",
    )
    parser.add_argument(
        "--prior-ledger",
        type=Path,
        action="append",
        default=[],
        help="prior harness CSV admitted only for tier authorization",
    )
    parser.add_argument(
        "--source-path",
        type=Path,
        action="append",
        default=[],
        help="source file included in the implementation bundle hash",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="root receiving outputs; protected identity is always read from the repository",
    )
    parser.add_argument(
        "--with-trace",
        action="store_true",
        help="opt out of the default summary-only mode",
    )
    return parser


def _tier_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(row.get("phase", "")),
        str(row.get("case_id", "")),
        int(row.get("size_segments", 0)),
    )


def _dedupe_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(dict(row))
    return result


def _replace_tiers(
    rows: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped = _dedupe_rows(replacements)
    keys = {_tier_key(row) for row in deduped}
    return [row for row in rows if _tier_key(row) not in keys] + deduped


def _merge_evidence_rows(
    planned: list[dict[str, Any]],
    prior: list[dict[str, Any]],
    executed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preserve admitted prior tiers; new execution atomically replaces a tier."""

    admitted_prior = [
        row
        for row in prior
        if row.get("execution_status") != "NOT_RUN"
        or row.get("evidence_status") in FROZEN_CONTROL_EVIDENCE_STATUSES
    ]
    merged = _replace_tiers(list(planned), admitted_prior)
    return _replace_tiers(merged, executed)


def _matches_current_provenance(
    row: Mapping[str, Any],
    *,
    binary_sha256: str,
    source_bundle_sha256_value: str,
    executor_source_sha256: str,
) -> bool:
    return (
        row.get("execution_status") != "NOT_RUN"
        and str(row.get("binary_sha256", "")) == binary_sha256
        and str(row.get("source_bundle_sha256", ""))
        == source_bundle_sha256_value
        and str(row.get("executor_source_sha256", ""))
        == executor_source_sha256
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    phases = _phases(args.phases)
    defined_cases = list(all_cases())
    cases = [case for case in defined_cases if case.phase in phases]
    if args.case_id:
        selected_ids = set(args.case_id)
        unknown = selected_ids - {case.case_id for case in cases}
        if unknown:
            raise ValueError(f"unknown selected case IDs: {sorted(unknown)}")
        execution_cases = [case for case in cases if case.case_id in selected_ids]
    else:
        execution_cases = list(cases)
    if args.repeat <= 0:
        raise ValueError("--repeat must be positive")
    if args.max_segments >= 8_192 and not args.allow_8192:
        raise PermissionError("--max-segments >=8192 requires --allow-8192")
    if args.max_segments == FULL_SIZE_SEGMENTS and not args.allow_full:
        raise PermissionError("full max size requires --allow-full")
    invalid_resources = set(args.promoted_resource) - set(RESOURCE_LABELS)
    if invalid_resources:
        raise ValueError(
            f"unknown --promoted-resource labels: {sorted(invalid_resources)}"
        )
    if len(set(args.promoted_resource)) > 2:
        raise ValueError(
            "--promoted-resource permits at most two reviewed 8192 resources"
        )

    planned = planned_results(cases)
    defined_controls = load_control_evidence(ROOT)
    controls = [row for row in defined_controls if row["phase"] in phases]
    known_case_ids = {
        *(case.case_id for case in defined_cases),
        *(str(row["case_id"]) for row in defined_controls),
    }
    accepted_rows: list[dict[str, Any]] = []
    for ledger in args.prior_ledger:
        accepted_rows.extend(
            row
            for row in load_result_ledger(ledger, root=ROOT)
            if row.get("phase") in ALL_PHASES
            and row.get("case_id") in known_case_ids
        )
    accepted_rows = apply_repeat_consistency(_dedupe_rows(accepted_rows))
    evidence_rows = _merge_evidence_rows(planned, accepted_rows, [])
    control_keys = {_tier_key(row) for row in controls}
    rows: list[dict[str, Any]] = [
        *controls,
        *(
            row
            for row in evidence_rows
            if _tier_key(row) not in control_keys
        ),
    ]
    executed_rows: list[dict[str, Any]] = []

    if args.execute:
        if args.binary is None:
            raise ValueError("--binary is required with --execute")
        executor = _executor(args.executor)
        source_paths = tuple(args.source_path) or DEFAULT_SOURCE_PATHS
        current_binary_sha256 = file_sha256(args.binary)
        current_source_bundle_sha256 = source_bundle_sha256(
            source_paths,
            root=ROOT,
        )
        current_executor_source_sha256 = inspect_executor(
            executor
        ).source_sha256
        if not current_executor_source_sha256:
            raise ValueError(
                "current executor source is not hashable; execution is blocked"
            )
        authorization_prior_rows = [
            row
            for row in accepted_rows
            if _matches_current_provenance(
                row,
                binary_sha256=current_binary_sha256,
                source_bundle_sha256_value=current_source_bundle_sha256,
                executor_source_sha256=current_executor_source_sha256,
            )
        ]
        nodes, edges, heuristic = canonical_graph_records(
            assert_canonical_map(CANONICAL_MAP_PATH)
        )
        base_kwargs: dict[str, Any] = {
            "node_records": nodes,
            "edge_records": edges,
            "heuristic_time": heuristic,
        }
        if args.search_path is not None:
            base_kwargs["search_path"] = args.search_path

        for case in execution_cases:
            for size in case.sizes:
                if size > args.max_segments:
                    continue
                replacement_rows = [
                    row
                    for row in executed_rows
                    if row.get("execution_status") != "NOT_RUN"
                ]
                authorization_rows = _replace_tiers(
                    authorization_prior_rows,
                    replacement_rows,
                )
                blockers = authorization_blockers(
                    case,
                    size,
                    authorization_rows,
                    allow_8192=args.allow_8192,
                    allow_full=args.allow_full,
                    promoted_resource_labels=args.promoted_resource,
                    promoted_finalists=args.promoted_finalist,
                    identity_root=ROOT,
                    required_repeat_count=args.repeat,
                )
                if blockers:
                    blocked = next(
                        row
                        for row in planned
                        if row["case_id"] == case.case_id
                        and int(row["size_segments"]) == size
                    )
                    blocked = dict(blocked)
                    blocked["blocker"] = " | ".join(blockers)
                    blocked["evidence_status"] = "AUTHORIZATION_BLOCKED_NOT_RUN"
                    executed_rows.append(blocked)
                    continue
                for _repeat_index in range(args.repeat):
                    result = execute_case(
                        case,
                        size,
                        executor=executor,
                        executor_binary=args.binary,
                        source_paths=source_paths,
                        base_runtime_kwargs=base_kwargs,
                        root=ROOT,
                        summary_only=not args.with_trace,
                    )
                    result["repeat_index"] = _repeat_index + 1
                    executed_rows.append(result)
                tier_start = len(executed_rows) - args.repeat
                executed_rows[tier_start:] = apply_repeat_consistency(
                    executed_rows[tier_start:]
                )
        replacement_rows = [
            row
            for row in executed_rows
            if row.get("execution_status") != "NOT_RUN"
        ]
        prior_keys = {_tier_key(row) for row in accepted_rows}
        new_pending_rows = [
            row
            for row in executed_rows
            if row.get("execution_status") == "NOT_RUN"
            and _tier_key(row) not in prior_keys
        ]
        evidence_rows = _merge_evidence_rows(
            planned,
            accepted_rows,
            replacement_rows,
        )
        evidence_rows = _replace_tiers(evidence_rows, new_pending_rows)
        rows = [
            *controls,
            *(
                row
                for row in evidence_rows
                if _tier_key(row) not in control_keys
            ),
        ]

    rows = apply_repeat_consistency(rows)
    paths = write_harness_outputs(
        rows,
        root=args.output_root,
        identity_root=ROOT,
    )
    return {
        "schema": RESULT_SCHEMA,
        "mode": "EXECUTE" if args.execute else "PLAN_ONLY",
        "phase_count": len(phases),
        "case_count": len(cases),
        "new_execution_row_count": sum(
            row.get("execution_status") not in {"NOT_RUN", ""}
            for row in executed_rows
        ),
        "pending_row_count": sum(
            row.get("execution_status") == "NOT_RUN"
            and row.get("gate_status") == "PENDING"
            for row in rows
        ),
        "output_paths": [path.resolve().as_posix() for path in paths],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
