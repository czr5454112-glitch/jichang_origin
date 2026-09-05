"""Audit the fixed-horizon destination-merge bijection failure signature.

This is a read-only diagnostic for the frozen targeted-ablation artifacts.  It
does not reinterpret business outcomes or waive an integrity gate.  Its only
purpose is to identify runs where the first false execution gate is the active
merge-grant bijection and the saved summary has the characteristic mixed
boundary: bags were terminalized for reporting while pre-cut active grants
remain recorded.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "outputs/runtime/cie_revision/targeted_ablation"

FIELDS = (
    "source_file",
    "map",
    "arm",
    "artifact_status",
    "execution_integrity_pass",
    "first_false_gate",
    "false_gates",
    "requested_count",
    "completed_count",
    "failed_count",
    "event_count",
    "decision_count",
    "time_limit_reached",
    "event_limit_reached",
    "final_active_bag_count",
    "merge_grant_final_active_unconsumed",
    "merge_grant_outstanding_request_count",
    "merge_grant_conservation_holds",
    "merge_grant_active_bijection_holds",
    "merge_grant_exact_slot_no_future_shift",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "diagnosis",
)

REPAIR_FIELDS = (
    "arm",
    "baseline_ref",
    "baseline_artifact_status",
    "current_artifact_status",
    "baseline_diagnosis",
    "current_diagnosis",
    "repair_status",
    "outcome_identity_match",
    "baseline_completed_count",
    "current_completed_count",
    "baseline_failed_count",
    "current_failed_count",
    "baseline_event_count",
    "current_event_count",
    "baseline_decision_count",
    "current_decision_count",
    "current_time_limit_reached",
    "current_event_limit_reached",
    "current_merge_grant_final_active_unconsumed",
    "current_merge_grant_outstanding_request_count",
    "current_merge_grant_conservation_holds",
    "current_merge_grant_active_bijection_holds",
    "current_merge_grant_exact_slot_no_future_shift",
    "baseline_binary_sha256",
    "current_binary_sha256",
    "current_workload_sha256",
    "current_base_request_sha256",
    "current_binary_matches_full_s4",
    "current_workload_matches_full_s4",
    "current_base_request_matches_full_s4",
    "current_identity_matches_full_s4",
    "current_wall_seconds",
    "current_cpu_seconds",
    "current_source_file",
)

CROSS_BOUNDARY_SIGNATURE = "CONSISTENT_WITH_CROSS_BOUNDARY_FINALIZATION_CHECK"
OTHER_FAILURE = "OTHER_OR_INSUFFICIENT_INTEGRITY_FAILURE"
NO_FAILURE = "NO_FALSE_EXECUTION_GATE"
REPAIRED = "REPAIRED_FIXED_HORIZON_TELEMETRY_IDENTITY"
UNCHANGED_PASS = "UNCHANGED_PASS"
REVIEW = "REVIEW_REQUIRED"


class BoundaryAuditError(RuntimeError):
    """Raised for malformed input, never for an observed failed run."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BoundaryAuditError(f"{label} must be an object")
    return value


def audit_payload(data: Mapping[str, Any], source: Path) -> dict[str, Any]:
    execution = _mapping(data.get("execution_integrity"), "execution_integrity")
    gates = _mapping(execution.get("gates"), "execution_integrity.gates")
    runtime = _mapping(data.get("runtime"), "runtime")
    summary = _mapping(runtime.get("native_summary"), "runtime.native_summary")
    algorithm = _mapping(data.get("algorithm"), "algorithm")
    provenance_value = data.get("provenance")
    provenance = provenance_value if isinstance(provenance_value, Mapping) else {}
    contract_value = data.get("ablation_contract")
    contract = contract_value if isinstance(contract_value, Mapping) else {}
    selection_value = data.get("selection_protocol")
    selection = selection_value if isinstance(selection_value, Mapping) else {}

    false_gates = [str(name) for name, value in gates.items() if value is False]
    signature = (
        false_gates == ["merge_grant_active_bijection"]
        and summary.get("time_limit_reached") is True
        and summary.get("event_limit_reached") is False
        and summary.get("final_active_bag_count") == 0
        and isinstance(summary.get("merge_grant_final_active_unconsumed"), int)
        and summary["merge_grant_final_active_unconsumed"] > 0
        and summary.get("merge_grant_conservation_holds") is True
        and summary.get("merge_grant_active_bijection_holds") is False
        and summary.get("reservation_conflicts") == 0
        and summary.get("physical_fault_edge_entry_violation_count") == 0
    )
    diagnosis = (
        CROSS_BOUNDARY_SIGNATURE
        if signature
        else (NO_FAILURE if not false_gates else OTHER_FAILURE)
    )
    return {
        "source_file": str(source.resolve()),
        "map": data.get("map"),
        "arm": algorithm.get("arm"),
        "artifact_status": data.get("status"),
        "execution_integrity_pass": execution.get("pass"),
        "first_false_gate": false_gates[0] if false_gates else "NA",
        "false_gates": ";".join(false_gates) if false_gates else "NA",
        "requested_count": summary.get("requested_count"),
        "completed_count": summary.get("completed_count"),
        "failed_count": summary.get("failed_count"),
        "event_count": summary.get("event_count"),
        "decision_count": summary.get("decision_count"),
        "time_limit_reached": summary.get("time_limit_reached"),
        "event_limit_reached": summary.get("event_limit_reached"),
        "final_active_bag_count": summary.get("final_active_bag_count"),
        "merge_grant_final_active_unconsumed": summary.get(
            "merge_grant_final_active_unconsumed"
        ),
        "merge_grant_outstanding_request_count": summary.get(
            "merge_grant_outstanding_request_count"
        ),
        "merge_grant_conservation_holds": summary.get(
            "merge_grant_conservation_holds"
        ),
        "merge_grant_active_bijection_holds": summary.get(
            "merge_grant_active_bijection_holds"
        ),
        "merge_grant_exact_slot_no_future_shift": summary.get(
            "merge_grant_exact_slot_no_future_shift"
        ),
        "reservation_conflicts": summary.get("reservation_conflicts"),
        "physical_fault_edge_entry_violation_count": summary.get(
            "physical_fault_edge_entry_violation_count"
        ),
        "binary_sha256": provenance.get("binary_sha256"),
        "binary_path": provenance.get("binary_path"),
        "workload_sha256": provenance.get("canonical_workload_sha256"),
        "workload_path": provenance.get("canonical_workload_path"),
        "base_request_sha256": contract.get("base_full_s4_request_sha256"),
        "activation_evidence_path": selection.get("activation_evidence_path"),
        "revision_manifest_path": provenance.get("revision_manifest_path"),
        "wall_seconds": runtime.get("wall_seconds"),
        "cpu_seconds": runtime.get("cpu_seconds"),
        "diagnosis": diagnosis,
    }


def audit_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryAuditError(f"cannot read {path}: {exc}") from exc
    return audit_payload(_mapping(data, "artifact"), path)


def audit_tree(input_root: Path) -> list[dict[str, Any]]:
    paths = sorted(input_root.glob("*/nanning_2x.json"))
    if not paths:
        raise BoundaryAuditError(f"no Nanning 2x artifacts under {input_root}")
    return [audit_file(path) for path in paths]


def audit_git_tree(input_root: Path, git_ref: str) -> list[dict[str, Any]]:
    paths = sorted(input_root.glob("*/nanning_2x.json"))
    if not paths:
        raise BoundaryAuditError(f"no Nanning 2x artifacts under {input_root}")
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise BoundaryAuditError(
                f"baseline audit path is outside the repository: {path}"
            ) from exc
        try:
            text = subprocess.check_output(
                ["git", "show", f"{git_ref}:{relative}"],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
            )
            data = json.loads(text)
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            raise BoundaryAuditError(
                f"cannot read baseline {git_ref}:{relative}: {exc}"
            ) from exc
        row = audit_payload(_mapping(data, "baseline artifact"), path)
        row["source_file"] = f"git:{git_ref}:{relative}"
        rows.append(row)
    return rows


def compare_repair_rows(
    baseline_rows: Sequence[Mapping[str, Any]],
    current_rows: Sequence[Mapping[str, Any]],
    baseline_ref: str,
) -> list[dict[str, Any]]:
    baseline = {str(row["arm"]): row for row in baseline_rows}
    current = {str(row["arm"]): row for row in current_rows}
    if baseline.keys() != current.keys():
        raise BoundaryAuditError("baseline/current Nanning arm sets differ")
    if "FULL_S4" not in current:
        raise BoundaryAuditError("current Nanning arm set has no FULL_S4 reference")
    current_reference = current["FULL_S4"]
    outcome_fields = (
        "requested_count",
        "completed_count",
        "failed_count",
        "event_count",
        "decision_count",
    )
    rows: list[dict[str, Any]] = []
    for arm in sorted(current):
        before = baseline[arm]
        after = current[arm]
        def valid_reference_match(field: str) -> bool:
            value = after.get(field)
            reference_value = current_reference.get(field)
            return (
                isinstance(value, str)
                and len(value) == 64
                and value == reference_value
            )

        binary_match = valid_reference_match("binary_sha256")
        workload_match = valid_reference_match("workload_sha256")
        base_request_match = valid_reference_match("base_request_sha256")
        current_identity_match = (
            binary_match and workload_match and base_request_match
        )
        outcome_match = all(
            before.get(name) == after.get(name) for name in outcome_fields
        )
        repaired = (
            before.get("diagnosis") == CROSS_BOUNDARY_SIGNATURE
            and after.get("diagnosis") == NO_FAILURE
            and after.get("execution_integrity_pass") is True
            and outcome_match
            and after.get("merge_grant_conservation_holds") is True
            and after.get("merge_grant_active_bijection_holds") is True
            and after.get("merge_grant_exact_slot_no_future_shift") is True
            and current_identity_match
        )
        unchanged_pass = (
            before.get("diagnosis") == NO_FAILURE
            and after.get("diagnosis") == NO_FAILURE
            and outcome_match
            and current_identity_match
        )
        status = (
            REPAIRED
            if repaired
            else (UNCHANGED_PASS if unchanged_pass else REVIEW)
        )
        rows.append(
            {
                "arm": arm,
                "baseline_ref": baseline_ref,
                "baseline_artifact_status": before.get("artifact_status"),
                "current_artifact_status": after.get("artifact_status"),
                "baseline_diagnosis": before.get("diagnosis"),
                "current_diagnosis": after.get("diagnosis"),
                "repair_status": status,
                "outcome_identity_match": outcome_match,
                "baseline_completed_count": before.get("completed_count"),
                "current_completed_count": after.get("completed_count"),
                "baseline_failed_count": before.get("failed_count"),
                "current_failed_count": after.get("failed_count"),
                "baseline_event_count": before.get("event_count"),
                "current_event_count": after.get("event_count"),
                "baseline_decision_count": before.get("decision_count"),
                "current_decision_count": after.get("decision_count"),
                "current_time_limit_reached": after.get("time_limit_reached"),
                "current_event_limit_reached": after.get("event_limit_reached"),
                "current_merge_grant_final_active_unconsumed": after.get(
                    "merge_grant_final_active_unconsumed"
                ),
                "current_merge_grant_outstanding_request_count": after.get(
                    "merge_grant_outstanding_request_count"
                ),
                "current_merge_grant_conservation_holds": after.get(
                    "merge_grant_conservation_holds"
                ),
                "current_merge_grant_active_bijection_holds": after.get(
                    "merge_grant_active_bijection_holds"
                ),
                "current_merge_grant_exact_slot_no_future_shift": after.get(
                    "merge_grant_exact_slot_no_future_shift"
                ),
                "baseline_binary_sha256": before.get("binary_sha256"),
                "current_binary_sha256": after.get("binary_sha256"),
                "current_workload_sha256": after.get("workload_sha256"),
                "current_base_request_sha256": after.get("base_request_sha256"),
                "current_binary_matches_full_s4": binary_match,
                "current_workload_matches_full_s4": workload_match,
                "current_base_request_matches_full_s4": base_request_match,
                "current_identity_matches_full_s4": current_identity_match,
                "current_wall_seconds": after.get("wall_seconds"),
                "current_cpu_seconds": after.get("cpu_seconds"),
                "current_source_file": after.get("source_file"),
                "binary_path": after.get("binary_path"),
                "workload_path": after.get("workload_path"),
                "activation_evidence_path": after.get("activation_evidence_path"),
                "revision_manifest_path": after.get("revision_manifest_path"),
            }
        )
    return rows


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({name: row.get(name) for name in FIELDS} for row in rows)


def write_repair_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REPAIR_FIELDS)
        writer.writeheader()
        writer.writerows(
            {name: row.get(name) for name in REPAIR_FIELDS} for row in rows
        )


def write_report(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    matched = [row for row in rows if row["diagnosis"] == CROSS_BOUNDARY_SIGNATURE]
    lines = [
        "# Fixed-horizon merge-boundary audit",
        "",
        f"Audited Nanning 2x cells: **{len(rows)}**; mixed-boundary signature: "
        f"**{len(matched)}**.",
        "",
        "This classification is diagnostic, not a gate waiver. It requires "
        "the active-bijection gate to be the sole false execution gate, a "
        "fixed-time (not event-count) stop, nonzero active grants, zero final "
        "active bags after reporting finalization, grant conservation, and "
        "zero reservation/physical-entry violations.",
        "",
        "| arm | first false gate | completed | failed | active grants | pending | diagnosis |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {arm} | {first_false_gate} | {completed_count} | "
            "{failed_count} | {merge_grant_final_active_unconsumed} | "
            "{merge_grant_outstanding_request_count} | {diagnosis} |".format(**row)
        )
    lines.extend(
        [
            "",
            "The C++ regression `test_fixed_horizon_checks_live_merge_boundary_before_reporting_failure` "
            "constructs the exact first-mismatch shape: one grant is committed "
            "and in transit at the last executable boundary; the fixed horizon "
            "then marks its bag as an incomplete reporting failure. The repair "
            "checks the bijection before that status-only finalization and does "
            "not consume, revoke, reroute, or complete the bag.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_repair_report(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    baseline_ref: str,
) -> None:
    repaired = [row for row in rows if row["repair_status"] == REPAIRED]
    review = [row for row in rows if row["repair_status"] == REVIEW]
    identity_closed = all(
        row["current_identity_matches_full_s4"] is True for row in rows
    )
    current_binary = sorted({str(row["current_binary_sha256"]) for row in rows})
    current_workload = sorted({str(row["current_workload_sha256"]) for row in rows})
    current_base_request = sorted(
        {str(row["current_base_request_sha256"]) for row in rows}
    )
    lines = [
        "# Fixed-horizon merge-boundary repair audit",
        "",
        f"Baseline: `{baseline_ref}`. Audited Nanning 2x cells: **{len(rows)}**; "
        f"repaired mixed-boundary cells: **{len(repaired)}**; review-required: "
        f"**{len(review)}**.",
        "",
        "This is a fixed-horizon telemetry-identity repair only. It changes "
        "neither routing actions nor completion outcomes: the active grant "
        "bijection is now checked at the last executable boundary, before "
        "unfinished bags are converted to fixed-denominator reporting failures. "
        "It is not an algorithmic performance improvement.",
        "",
        "| arm | before | after | completed old/new | failed old/new | time limit | active grants | pending | conservation | bijection | exact slot | current identity vs FULL_S4 | verdict |",
        "|---|---|---|---:|---:|---|---:|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {arm} | {baseline_diagnosis} | {current_diagnosis} | "
            "{baseline_completed_count}/{current_completed_count} | "
            "{baseline_failed_count}/{current_failed_count} | "
            "{current_time_limit_reached} | "
            "{current_merge_grant_final_active_unconsumed} | "
            "{current_merge_grant_outstanding_request_count} | "
            "{current_merge_grant_conservation_holds} | "
            "{current_merge_grant_active_bijection_holds} | "
            "{current_merge_grant_exact_slot_no_future_shift} | "
            "{current_identity_matches_full_s4} | "
            "{repair_status} |".format(**row)
        )
    lines.extend(
        [
            "",
            "The tracked evidence identifies `FULL_MINUS_Q`, `FULL_MINUS_WS`, "
            "and `H_PLUS_Q_PLUS_I` as the three failed cells. `FULL_MINUS_I` "
            "was already a passing cell in the baseline; any instruction "
            "listing it as failed is inconsistent with the executable artifacts.",
            "",
            "Current executed-arm identity closure against `FULL_S4`: "
            f"**{identity_closed}**. Binary SHA256: "
            f"`{current_binary[0] if len(current_binary) == 1 else current_binary}`; "
            "workload SHA256: "
            f"`{current_workload[0] if len(current_workload) == 1 else current_workload}`; "
            "base-request SHA256: "
            f"`{current_base_request[0] if len(current_base_request) == 1 else current_base_request}`. "
            "A mixed current identity is review-required and cannot enter the paired table.",
            "",
            "All 2x THT values remain protocol-level `NA`; no survivor/common-"
            "cohort timing is introduced.",
            "",
            "## Exact rerun commands",
            "",
        ]
    )
    for row in rows:
        lines.append(
            "```powershell\n"
            "python scripts/eval/run_cie_targeted_ablation.py --map nanning "
            f"--scale 2 --arm {row['arm']} --canonical \"{row['workload_path']}\" "
            f"--binary \"{row['binary_path']}\" --activation-evidence "
            f"\"{row['activation_evidence_path']}\" --revision-manifest "
            f"\"{row['revision_manifest_path']}\" --output "
            f"\"{row['current_source_file']}\" --force\n```"
        )
    lines.extend(
        [
            "",
            "The focused C++ regression constructs one exact grant in transit "
            "at a time cut and proves that the bag remains an honest "
            "`time_limit_reached` failure while the pre-finalization "
            "controller/capability/bag/calendar bijection passes.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--baseline-ref",
        help="Optional git ref for a before/after repair audit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rows = audit_tree(args.input_root)
    if args.baseline_ref:
        baseline = audit_git_tree(args.input_root, args.baseline_ref)
        compared = compare_repair_rows(baseline, rows, args.baseline_ref)
        if args.csv is not None:
            write_repair_csv(args.csv, compared)
        if args.report is not None:
            write_repair_report(args.report, compared, args.baseline_ref)
        repaired = sum(row["repair_status"] == REPAIRED for row in compared)
        review = sum(row["repair_status"] == REVIEW for row in compared)
        print(
            json.dumps(
                {"audited": len(compared), "repaired": repaired, "review": review},
                sort_keys=True,
            )
        )
        return 0 if review == 0 else 2
    if args.csv is not None:
        write_csv(args.csv, rows)
    if args.report is not None:
        write_report(args.report, rows)
    matched = sum(row["diagnosis"] == CROSS_BOUNDARY_SIGNATURE for row in rows)
    print(json.dumps({"audited": len(rows), "matched": matched}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BoundaryAuditError as exc:
        print(f"fixed-horizon merge-boundary audit failed: {exc}")
        raise SystemExit(2)
