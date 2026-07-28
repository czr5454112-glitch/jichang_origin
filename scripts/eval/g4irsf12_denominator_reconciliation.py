"""Append-only reconciliation for the G4IRSF12 original-entry gate.

The formal G4IRSF12 harness is intentionally not modified here because it is
part of the sealed execution source bundle.  This module re-admits the sealed
Phase-J ledger, verifies the historical G4IRSF8 comparator provenance, and
translates the legacy pass-time-anchored baselines onto the true raw-task
``original_entry_time`` denominator.

No runtime is executed and no sealed evidence is rewritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts.eval.g4irsf12_phase_a import (
    EXPECTED_HCA_MEANS,
    EXPECTED_V2_SAFE_MEANS,
    SOURCE_SHA256,
)
from scripts.eval.g4irsf12_reproducible_harness import (
    CANDIDATE_BUNDLE_SCHEMA,
    FORMAL_SOURCE_PATHS,
    ExecutionProvenance,
    canonical_sha256,
    execution_provenance_matches,
    load_result_ledger,
    source_bundle_sha256,
)
from scripts.eval.g4irsf12_size_ladder import (
    FULL_SIZE_BAGS,
    FULL_SIZE_SEGMENTS,
)

ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "czr005.g4irsf12.denominator_reconciliation.v1"
STATUS = "VERIFIED_DENOMINATOR_MISMATCH"
RECONCILIATION_SCRIPT_PATH = Path(
    "scripts/eval/g4irsf12_denominator_reconciliation.py"
)
SOURCE_PATH = Path("data/processed/tasks/inputdata.jsonl")
LEDGER_PATH = Path("outputs/tables/g4irsf12_original_scale_full_ab.csv")
LEGACY_TABLE_PATH = Path(
    "outputs/tables/g4irsf8_tth_denominator_comparison.csv"
)
LEGACY_RECOMPUTE_SOURCE_PATH = Path(
    "scripts/eval/run_g4irsf8_source_release_denominator_validation.py"
)
CANDIDATE_BUNDLE_PATH = Path(
    "artifacts/policies/g4irsf12_original_scale_candidate_bundle.json"
)

POLICY_OUTPUT_PATH = Path(
    "artifacts/policies/g4irsf12_denominator_reconciliation.json"
)
TABLE_OUTPUT_PATH = Path(
    "outputs/tables/g4irsf12_denominator_reconciliation.csv"
)
REPORT_OUTPUT_PATH = Path(
    "outputs/reports/g4irsf12_denominator_reconciliation.md"
)

FINALIST_IDS = ("J_F1", "J_F2")
LEGACY_ENTRY_ASSIGNMENT = '"entry_time": float(source["pass_time"])'
LEGACY_ENTRY_READ = 'start = row.get("entry_time")'
EXPECTED_LEDGER_SHA256 = (
    "0263e022a32936423023013d6eaaa2e3140e44757280ef84c67cf91b59986f0c"
)
EXPECTED_CANDIDATE_BUNDLE_FILE_SHA256 = (
    "d886127f1a04def63e1bab54751385f088e68598500863c61c14a35368bd6756"
)
EXPECTED_LEGACY_TABLE_SHA256 = (
    "d496e733c247092d03ed247ca524f1ec83a63cfab5d64adcd4c64fd2a7b653f6"
)
EXPECTED_LEGACY_RECOMPUTE_SOURCE_SHA256 = (
    "f4ccb6ef64451c4fa7f038f6b1260175674e4df8a866476c8abc7e7bd48a68f9"
)

SUPERSEDED_FIELDS = (
    "outputs/tables/g4irsf12_original_scale_full_ab.csv:"
    "v2_safe_original_entry_target_minutes",
    "outputs/tables/g4irsf12_original_scale_full_ab.csv:"
    "v2_safe_original_entry_gate",
    "outputs/tables/g4irsf12_original_scale_full_ab.csv:"
    "corrected_hca_original_entry_target_minutes",
    "outputs/tables/g4irsf12_original_scale_full_ab.csv:"
    "corrected_hca_original_entry_gate",
    "outputs/tables/g4irsf12_original_scale_full_ab.csv:"
    "matched_original_entry_performance_gate",
    "artifacts/policies/g4irsf12_original_scale_candidate_bundle.json:"
    "performance targets, performance gates, and derived blockers",
    "outputs/reports/g4irsf12_original_scale_full_ab.md:"
    "performance-target interpretation",
    "outputs/reports/g4irsf12_promotion_gate.md:"
    "performance-target interpretation",
)

TABLE_COLUMNS = (
    "schema",
    "status",
    "candidate_id",
    "executed_full_repeat_count",
    "deterministic_result_sha256",
    "original_entry_mean_minutes",
    "pass_time_anchored_mean_minutes",
    "scheduled_pre_release_offset_minutes",
    "corrected_v2_safe_raw_entry_target_minutes",
    "delta_vs_v2_minutes",
    "delta_vs_v2_seconds",
    "v2_safe_raw_entry_gate",
    "corrected_hca_raw_entry_target_minutes",
    "delta_vs_hca_minutes",
    "hca_advantage_minutes",
    "corrected_hca_raw_entry_gate",
    "safety_termination_gate",
    "strict_joint_promotion_gate",
    "g4j_status",
)


class ReconciliationError(RuntimeError):
    """Raised when any evidence needed by the reconciliation is inconsistent."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise ReconciliationError(f"missing reconciliation input: {path}")
    return _sha256(path.read_bytes())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ReconciliationError(f"expected JSON object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ReconciliationError(f"missing reconciliation input: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _one_row(
    rows: Sequence[Mapping[str, Any]],
    **criteria: str,
) -> Mapping[str, Any]:
    matches = [
        row
        for row in rows
        if all(str(row.get(key, "")) == value for key, value in criteria.items())
    ]
    if len(matches) != 1:
        raise ReconciliationError(
            f"expected exactly one row for {criteria}, found {len(matches)}"
        )
    return matches[0]


def _provenance_from_bundle(bundle: Mapping[str, Any]) -> ExecutionProvenance:
    raw = bundle.get("current_provenance")
    if not isinstance(raw, Mapping):
        raise ReconciliationError("candidate bundle current_provenance is missing")
    try:
        return ExecutionProvenance(
            binary_path=str(raw["binary_path"]),
            binary_sha256=str(raw["binary_sha256"]),
            source_bundle_sha256=str(raw["source_bundle_sha256"]),
            source_path_manifest_sha256=str(
                raw["source_path_manifest_sha256"]
            ),
            executor_id=str(raw["executor_id"]),
            executor_source_sha256=str(raw["executor_source_sha256"]),
        )
    except KeyError as exc:
        raise ReconciliationError(
            f"candidate bundle provenance lacks {exc.args[0]}"
        ) from exc


def _input_offset(root: Path) -> dict[str, Any]:
    path = root / SOURCE_PATH
    source_sha = _file_sha256(path)
    if source_sha != SOURCE_SHA256:
        raise ReconciliationError(
            f"protected source SHA drift: {source_sha} != {SOURCE_SHA256}"
        )

    task_entry: dict[int, float] = {}
    pre_release_by_task: dict[int, float] = defaultdict(float)
    segment_ids: set[str] = set()
    leg_counts: Counter[str] = Counter()
    leg_wait_seconds: dict[str, float] = defaultdict(float)
    segment_count = 0

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReconciliationError(
                    f"{SOURCE_PATH}:{line_number}: invalid JSON"
                ) from exc
            if not isinstance(row, dict):
                raise ReconciliationError(
                    f"{SOURCE_PATH}:{line_number}: expected object"
                )
            try:
                task_id = int(row["task_id"])
                segment_id = str(row["segment_id"])
                original_entry = float(row["original_entry_time"])
                pass_time = float(row["pass_time"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ReconciliationError(
                    f"{SOURCE_PATH}:{line_number}: invalid timing identity"
                ) from exc
            if segment_id in segment_ids:
                raise ReconciliationError(f"duplicate segment_id: {segment_id}")
            segment_ids.add(segment_id)
            if not all(math.isfinite(value) for value in (original_entry, pass_time)):
                raise ReconciliationError(
                    f"{segment_id}: non-finite entry/release time"
                )
            if pass_time + 1.0e-9 < original_entry:
                raise ReconciliationError(
                    f"{segment_id}: pass_time precedes original_entry_time"
                )
            prior_entry = task_entry.setdefault(task_id, original_entry)
            if not math.isclose(
                prior_entry,
                original_entry,
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                raise ReconciliationError(
                    f"task {task_id}: raw original-entry time is not common"
                )
            wait = pass_time - original_entry
            pre_release_by_task[task_id] += wait
            leg = str(row.get("leg", ""))
            leg_counts[leg] += 1
            leg_wait_seconds[leg] += wait
            segment_count += 1

    if segment_count != FULL_SIZE_SEGMENTS:
        raise ReconciliationError(
            f"protected segment count {segment_count} != {FULL_SIZE_SEGMENTS}"
        )
    if len(task_entry) != FULL_SIZE_BAGS:
        raise ReconciliationError(
            f"protected raw-bag count {len(task_entry)} != {FULL_SIZE_BAGS}"
        )
    if set(pre_release_by_task) != set(task_entry):
        raise ReconciliationError("pre-release task population is incomplete")

    offset_minutes = (
        statistics.fmean(pre_release_by_task.values()) / 60.0
    )
    return {
        "path": SOURCE_PATH.as_posix(),
        "file_sha256": source_sha,
        "segment_count": segment_count,
        "raw_bag_count": len(task_entry),
        "scheduled_pre_release_offset_minutes": offset_minutes,
        "leg_counts": dict(sorted(leg_counts.items())),
        "leg_pre_release_wait_seconds": {
            key: leg_wait_seconds[key] for key in sorted(leg_wait_seconds)
        },
    }


def _legacy_baselines(root: Path) -> dict[str, Any]:
    table_path = root / LEGACY_TABLE_PATH
    source_path = root / LEGACY_RECOMPUTE_SOURCE_PATH
    table_sha = _file_sha256(table_path)
    source_sha = _file_sha256(source_path)
    if table_sha != EXPECTED_LEGACY_TABLE_SHA256:
        raise ReconciliationError(
            "legacy denominator table SHA drift: "
            f"{table_sha} != {EXPECTED_LEGACY_TABLE_SHA256}"
        )
    if source_sha != EXPECTED_LEGACY_RECOMPUTE_SOURCE_SHA256:
        raise ReconciliationError(
            "legacy denominator reducer SHA drift: "
            f"{source_sha} != {EXPECTED_LEGACY_RECOMPUTE_SOURCE_SHA256}"
        )
    rows = _read_csv(table_path)
    source_text = source_path.read_text(encoding="utf-8")
    if LEGACY_ENTRY_ASSIGNMENT not in source_text:
        raise ReconciliationError(
            "legacy HCA alignment no longer maps source pass_time to entry_time"
        )
    if LEGACY_ENTRY_READ not in source_text:
        raise ReconciliationError(
            "legacy original-entry reducer no longer reads aligned entry_time"
        )

    v2_row = _one_row(
        rows,
        variant="java_source_queue_one_per_epoch",
        tth_denominator="original_entry_time_tth",
    )
    hca_row = _one_row(
        rows,
        variant="original_project_text_result",
        tth_denominator="original_entry_time_tth",
    )
    for label, row, expected in (
        (
            "v2-safe",
            v2_row,
            EXPECTED_V2_SAFE_MEANS["original_entry_time_tth"],
        ),
        (
            "historical HCA",
            hca_row,
            EXPECTED_HCA_MEANS["original_entry_time_tth"],
        ),
    ):
        if int(row["complete_bags"]) != FULL_SIZE_BAGS:
            raise ReconciliationError(
                f"{label} legacy comparator is not full-bag evidence"
            )
        if not math.isclose(
            float(row["mean_tht"]),
            expected,
            rel_tol=0.0,
            abs_tol=5.0e-9,
        ):
            raise ReconciliationError(
                f"{label} legacy comparator value drift"
            )

    return {
        "table_path": LEGACY_TABLE_PATH.as_posix(),
        "table_file_sha256": table_sha,
        "recompute_source_path": LEGACY_RECOMPUTE_SOURCE_PATH.as_posix(),
        "recompute_source_file_sha256": source_sha,
        "legacy_label": "original_entry_time_tth",
        "actual_start_field": "data/processed/tasks/inputdata.jsonl:pass_time",
        "v2_safe_pass_time_anchored_minutes": (
            EXPECTED_V2_SAFE_MEANS["original_entry_time_tth"]
        ),
        "historical_hca_pass_time_anchored_minutes": (
            EXPECTED_HCA_MEANS["original_entry_time_tth"]
        ),
        "historical_hca_is_fresh_rerun": False,
    }


def _finalist_safety_termination_pass(row: Mapping[str, Any]) -> bool:
    """Require complete, safe, uncensored execution evidence for one finalist."""

    try:
        return (
            str(row.get("execution_status", "")) == "EXECUTED"
            and row.get("comparison_eligible") is True
            and int(row.get("complete_raw_bag_count", -1)) == FULL_SIZE_BAGS
            and int(row.get("completed_segment_count", -1))
            == FULL_SIZE_SEGMENTS
            and int(row.get("failed_segment_count", -1)) == 0
            and math.isclose(
                float(row.get("completion_rate", math.nan)),
                1.0,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            and int(row.get("conflict_count", -1)) == 0
            and int(row.get("unsafe_entry_count", -1)) == 0
            and int(row.get("unresolved_deadlock_count", -1)) == 0
            and str(row.get("termination_reason", "")) == "DRAINED"
            and row.get("event_limit_reached") is False
            and row.get("time_limit_reached") is False
            and str(row.get("early_abort_status", "")) == ""
            and row.get("binary_provenance_pass") is True
            and row.get("summary_only") is True
            and row.get("summary_only_contract_pass") is True
            and str(row.get("repeat_consistency", "")) == "MATCH"
        )
    except (TypeError, ValueError):
        return False


def _pibt_off_censored_deadlock_signature(
    row: Mapping[str, Any],
) -> bool:
    """Recognize the bounded PIBT-off completion/deadlock failure signature."""

    try:
        complete_raw_bags = int(row.get("complete_raw_bag_count", -1))
        completed_segments = int(row.get("completed_segment_count", -1))
        failed_segments = int(row.get("failed_segment_count", -1))
        event_count = int(row.get("event_count", -1))
        declared_max_events = int(row.get("declared_max_events", -1))
        max_events_echo = int(row.get("max_events_echo", -1))
        return (
            str(row.get("execution_status", "")) == "PARTIAL"
            and row.get("comparison_eligible") is False
            and 0 <= complete_raw_bags < FULL_SIZE_BAGS
            and 0 <= completed_segments < FULL_SIZE_SEGMENTS
            and failed_segments == FULL_SIZE_SEGMENTS - completed_segments
            and math.isclose(
                float(row.get("completion_rate", math.nan)),
                complete_raw_bags / FULL_SIZE_BAGS,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            and int(row.get("unresolved_deadlock_count", 0)) > 0
            and str(row.get("termination_reason", "")) == "EVENT_LIMIT"
            and row.get("event_limit_reached") is True
            and row.get("time_limit_reached") is False
            and event_count == declared_max_events
            and declared_max_events == max_events_echo
            and declared_max_events > 0
            and str(row.get("early_abort_status", "")) == ""
            and row.get("binary_provenance_pass") is True
            and row.get("summary_only") is True
            and row.get("summary_only_contract_pass") is True
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return False


def _candidate_rows(
    root: Path,
    *,
    offset_minutes: float,
    corrected_v2_target: float,
    corrected_hca_target: float,
    legacy_v2_target: float,
    legacy_hca_target: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ledger_path = root / LEDGER_PATH
    bundle_path = root / CANDIDATE_BUNDLE_PATH
    ledger_sha = _file_sha256(ledger_path)
    bundle_file_sha = _file_sha256(bundle_path)
    if ledger_sha != EXPECTED_LEDGER_SHA256:
        raise ReconciliationError(
            f"sealed Phase-J ledger SHA drift: {ledger_sha}"
        )
    if bundle_file_sha != EXPECTED_CANDIDATE_BUNDLE_FILE_SHA256:
        raise ReconciliationError(
            f"sealed Phase-J candidate bundle SHA drift: {bundle_file_sha}"
        )
    bundle = _read_object(bundle_path)
    if bundle.get("schema") != CANDIDATE_BUNDLE_SCHEMA:
        raise ReconciliationError("candidate bundle schema drift")
    recorded_bundle_sha = str(bundle.get("bundle_sha256", ""))
    unhashed_bundle = dict(bundle)
    unhashed_bundle.pop("bundle_sha256", None)
    if canonical_sha256(unhashed_bundle) != recorded_bundle_sha:
        raise ReconciliationError("candidate bundle self-hash mismatch")
    provenance = _provenance_from_bundle(bundle)
    current_source_bundle = source_bundle_sha256(
        FORMAL_SOURCE_PATHS,
        root=root,
    )
    if current_source_bundle != provenance.source_bundle_sha256:
        raise ReconciliationError(
            "formal source bundle drift; sealed execution is no longer current"
        )

    admitted = load_result_ledger(ledger_path, root=root)
    corrected: list[dict[str, Any]] = []
    for candidate_id in FINALIST_IDS:
        rows = [
            row
            for row in admitted
            if row.get("candidate_id") == candidate_id
            and int(row.get("size_segments", 0)) == FULL_SIZE_SEGMENTS
            and execution_provenance_matches(
                row,
                provenance,
                require_binary_file=False,
            )
        ]
        repeat_indexes = sorted(int(row["repeat_index"]) for row in rows)
        hashes = {
            str(row["deterministic_result_sha256"]) for row in rows
        }
        if len(rows) != 5 or repeat_indexes != [1, 2, 3, 4, 5]:
            raise ReconciliationError(
                f"{candidate_id}: expected exact full repeat indexes 1..5"
            )
        if any(row.get("execution_status") != "EXECUTED" for row in rows):
            raise ReconciliationError(
                f"{candidate_id}: finalist repeat is not fully executed"
            )
        if len(hashes) != 1 or "" in hashes:
            raise ReconciliationError(
                f"{candidate_id}: deterministic repeat hash mismatch"
            )
        original_means = {
            float(row["original_entry_mean_minutes"]) for row in rows
        }
        pass_time_means = {
            float(row["java_release_mean_minutes"]) for row in rows
        }
        if len(original_means) != 1 or len(pass_time_means) != 1:
            raise ReconciliationError(
                f"{candidate_id}: timing means are not deterministic"
            )
        if not all(
            row.get("comparison_eligible") is True
            and int(row["complete_raw_bag_count"]) == FULL_SIZE_BAGS
            and int(row["completed_segment_count"]) == FULL_SIZE_SEGMENTS
            for row in rows
        ):
            raise ReconciliationError(
                f"{candidate_id}: full-population comparison is incomplete"
            )
        safety_termination_pass = all(
            _finalist_safety_termination_pass(row) for row in rows
        )
        original_mean = next(iter(original_means))
        pass_time_mean = next(iter(pass_time_means))
        if not math.isclose(
            original_mean - pass_time_mean,
            offset_minutes,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        ):
            raise ReconciliationError(
                f"{candidate_id}: raw/pass-time decomposition mismatch"
            )

        v2_pass = original_mean <= corrected_v2_target
        hca_pass = original_mean <= corrected_hca_target
        if v2_pass != (pass_time_mean <= legacy_v2_target):
            raise ReconciliationError(
                f"{candidate_id}: v2 translation is not algebraically invariant"
            )
        if hca_pass != (pass_time_mean <= legacy_hca_target):
            raise ReconciliationError(
                f"{candidate_id}: HCA translation is not algebraically invariant"
            )
        corrected.append(
            {
                "schema": SCHEMA,
                "status": STATUS,
                "candidate_id": candidate_id,
                "executed_full_repeat_count": 5,
                "deterministic_result_sha256": next(iter(hashes)),
                "original_entry_mean_minutes": original_mean,
                "pass_time_anchored_mean_minutes": pass_time_mean,
                "scheduled_pre_release_offset_minutes": offset_minutes,
                "corrected_v2_safe_raw_entry_target_minutes": (
                    corrected_v2_target
                ),
                "delta_vs_v2_minutes": original_mean - corrected_v2_target,
                "delta_vs_v2_seconds": (
                    original_mean - corrected_v2_target
                )
                * 60.0,
                "v2_safe_raw_entry_gate": "PASS" if v2_pass else "FAIL",
                "corrected_hca_raw_entry_target_minutes": (
                    corrected_hca_target
                ),
                "delta_vs_hca_minutes": original_mean - corrected_hca_target,
                "hca_advantage_minutes": corrected_hca_target - original_mean,
                "corrected_hca_raw_entry_gate": (
                    "PASS" if hca_pass else "FAIL"
                ),
                "safety_termination_gate": (
                    "PASS" if safety_termination_pass else "FAIL"
                ),
                "strict_joint_promotion_gate": (
                    "PASS"
                    if v2_pass and hca_pass and safety_termination_pass
                    else "FAIL"
                ),
                "g4j_status": "CLOSED",
            }
        )

    control_rows = [
        row
        for row in admitted
        if row.get("candidate_id") == "J_CTRL_PIBT_OFF"
        and int(row.get("size_segments", 0)) == FULL_SIZE_SEGMENTS
        and execution_provenance_matches(
            row,
            provenance,
            require_binary_file=False,
        )
    ]
    if len(control_rows) != 5:
        raise ReconciliationError("PIBT-off control lacks five admitted repeats")
    if any(row.get("execution_status") != "PARTIAL" for row in control_rows):
        raise ReconciliationError(
            "PIBT-off control repeat is not retained as partial evidence"
        )
    control_repeat_indexes = sorted(
        int(row["repeat_index"]) for row in control_rows
    )
    if control_repeat_indexes != [1, 2, 3, 4, 5]:
        raise ReconciliationError(
            "PIBT-off control lacks exact repeat indexes 1..5"
        )
    control_hashes = {
        str(row.get("deterministic_result_sha256", ""))
        for row in control_rows
    }
    if len(control_hashes) != 1 or "" in control_hashes:
        raise ReconciliationError(
            "PIBT-off control deterministic repeat hash mismatch"
        )
    control_signature_pass = all(
        _pibt_off_censored_deadlock_signature(row) for row in control_rows
    )
    control = {
        "candidate_id": "J_CTRL_PIBT_OFF",
        "executed_repeat_count": len(control_rows),
        "repeat_indexes": control_repeat_indexes,
        "deterministic_result_sha256": next(iter(control_hashes)),
        "execution_statuses": sorted(
            {str(row["execution_status"]) for row in control_rows}
        ),
        "completed_segment_count": sorted(
            {int(row["completed_segment_count"]) for row in control_rows}
        ),
        "complete_raw_bag_count": sorted(
            {int(row["complete_raw_bag_count"]) for row in control_rows}
        ),
        "unresolved_deadlock_count": sorted(
            {int(row["unresolved_deadlock_count"]) for row in control_rows}
        ),
        "event_limit_reached": all(
            bool(row["event_limit_reached"]) for row in control_rows
        ),
        "censored_deadlock_signature_gate": (
            "PASS" if control_signature_pass else "FAIL"
        ),
    }
    return corrected, {
        "path": LEDGER_PATH.as_posix(),
        "file_sha256": ledger_sha,
        "admitted_row_count": len(admitted),
        "formal_source_bundle_sha256": current_source_bundle,
        "candidate_bundle_path": CANDIDATE_BUNDLE_PATH.as_posix(),
        "candidate_bundle_file_sha256": bundle_file_sha,
        "candidate_bundle_self_sha256": recorded_bundle_sha,
        "pibt_off_control": control,
    }


def build_reconciliation(root: Path = ROOT) -> dict[str, Any]:
    """Build and validate the append-only denominator correction."""

    if RECONCILIATION_SCRIPT_PATH in FORMAL_SOURCE_PATHS:
        raise ReconciliationError(
            "reconciliation script must not alter formal execution provenance"
        )
    input_evidence = _input_offset(root)
    legacy = _legacy_baselines(root)
    offset = float(
        input_evidence["scheduled_pre_release_offset_minutes"]
    )
    legacy_v2 = float(legacy["v2_safe_pass_time_anchored_minutes"])
    legacy_hca = float(
        legacy["historical_hca_pass_time_anchored_minutes"]
    )
    corrected_v2 = legacy_v2 + offset
    corrected_hca = legacy_hca + offset
    finalists, sealed_evidence = _candidate_rows(
        root,
        offset_minutes=offset,
        corrected_v2_target=corrected_v2,
        corrected_hca_target=corrected_hca,
        legacy_v2_target=legacy_v2,
        legacy_hca_target=legacy_hca,
    )

    safety_pass = all(
        row["safety_termination_gate"] == "PASS" for row in finalists
    )
    hca_performance_pass = all(
        row["corrected_hca_raw_entry_gate"] == "PASS"
        for row in finalists
    )
    v2_performance_pass = all(
        row["v2_safe_raw_entry_gate"] == "PASS" for row in finalists
    )
    control_signature_pass = (
        sealed_evidence["pibt_off_control"][
            "censored_deadlock_signature_gate"
        ]
        == "PASS"
    )
    hca_pass = safety_pass and hca_performance_pass
    v2_pass = safety_pass and v2_performance_pass
    pibt_off_pass = safety_pass and control_signature_pass
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "method": "append_only_algebraic_denominator_translation",
        "runtime_rerun_required": False,
        "sealed_execution_evidence_rewritten": False,
        "formal_source_bundle_preserved": True,
        "formula": (
            "matched_raw_entry_target = legacy_pass_time_anchored_target + "
            "mean_task(sum_segment(pass_time-original_entry_time))/60"
        ),
        "input_evidence": input_evidence,
        "legacy_comparator_evidence": legacy,
        "sealed_phase_j_evidence": sealed_evidence,
        "corrected_targets": {
            "scheduled_pre_release_offset_minutes": offset,
            "v2_safe_raw_entry_target_minutes": corrected_v2,
            "historical_hca_raw_entry_target_minutes": corrected_hca,
        },
        "finalists": finalists,
        "decision": {
            "new_framework_plus_decentralized_vs_historical_hca": (
                "PASS" if hca_pass else "FAIL"
            ),
            "new_framework_plus_decentralized_vs_frozen_v2_safe": (
                "PASS" if v2_pass else "FAIL"
            ),
            "new_framework_plus_decentralized_vs_pibt_off_control": (
                "PASS" if pibt_off_pass else "FAIL"
            ),
            "strict_joint_promotion_gate": (
                "PASS"
                if safety_pass
                and hca_performance_pass
                and v2_performance_pass
                else "FAIL"
            ),
            "historical_hca_claim_boundary": (
                "parsed historical evidence; not a same-machine fresh rerun"
            ),
            "pibt_off_claim_boundary": (
                "completion/deadlock only; control TTH is event-limit censored"
            ),
            "repeat_claim_boundary": (
                "five deterministic reproductions; not independent trials"
            ),
            "g4j_status": "CLOSED",
            "phase_k_multiplier": "UNKNOWN_NOT_COMPUTABLE",
            "phase_l_status": "BLOCKED_NOT_RUN",
        },
        "legacy_gate_status": "SUPERSEDED_DENOMINATOR_MISMATCH",
        "superseded_fields": list(SUPERSEDED_FIELDS),
        "preserved_evidence_fields": [
            "runtime timing observations",
            "completion and drainage counts",
            "safety/conflict/deadlock counters",
            "repeat indexes and deterministic result hashes",
            "binary and formal execution provenance",
        ],
    }
    payload["reconciliation_sha256"] = canonical_sha256(payload)
    return payload


def _table_bytes(payload: Mapping[str, Any]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(TABLE_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in payload["finalists"]:
        writer.writerow({column: row.get(column, "") for column in TABLE_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def _report_bytes(payload: Mapping[str, Any]) -> bytes:
    targets = payload["corrected_targets"]
    input_evidence = payload["input_evidence"]
    sealed = payload["sealed_phase_j_evidence"]
    control = sealed["pibt_off_control"]
    lines = [
        "# G4IRSF12 Denominator Reconciliation",
        "",
        f"Status: `{payload['status']}`.",
        "",
        "This append-only audit supersedes the old Phase-J performance-target "
        "interpretation. It does not modify the sealed runtime ledger, result "
        "hashes, safety evidence, or formal execution provenance.",
        "",
        "## Root cause",
        "",
        "G4IRSF8 labelled `inputdata.jsonl:pass_time` as "
        "`original_entry_time_tth`. G4IRSF12 correctly introduced the distinct "
        "raw-task `original_entry_time` and included the scheduled dwell before "
        "later storage-out segments become eligible. Directly comparing the new "
        "raw-entry mean with the old pass-time-anchored targets therefore added "
        "a fixed input-side offset only to the candidates.",
        "",
        "```text",
        "scheduled_pre_release",
        "  = mean_task(sum_segment(pass_time - original_entry_time)) / 60",
        f"  = {targets['scheduled_pre_release_offset_minutes']:.15f} min",
        "",
        "matched raw-entry target = legacy target + scheduled_pre_release",
        f"v2-safe = {targets['v2_safe_raw_entry_target_minutes']:.15f} min",
        f"HCA*    = {targets['historical_hca_raw_entry_target_minutes']:.15f} min",
        "```",
        "",
        "The offset is computed from the protected "
        f"{input_evidence['segment_count']:,}-segment / "
        f"{input_evidence['raw_bag_count']:,}-bag population. It is fixed by "
        "the input and is not algorithmic queueing.",
        "",
        "## Corrected matched comparison",
        "",
        "| Candidate | Raw-entry mean | vs frozen v2 | v2 gate | "
        "vs historical HCA* | HCA gate | Safety/termination | Joint gate |",
        "| --- | ---: | ---: | --- | ---: | --- | --- | --- |",
    ]
    for row in payload["finalists"]:
        v2_seconds = float(row["delta_vs_v2_seconds"])
        hca_advantage = float(row["hca_advantage_minutes"])
        lines.append(
            f"| {row['candidate_id']} | "
            f"{float(row['original_entry_mean_minutes']):.9f} min | "
            f"{v2_seconds:+.3f} s | {row['v2_safe_raw_entry_gate']} | "
            f"{hca_advantage:.6f} min faster | "
            f"{row['corrected_hca_raw_entry_gate']} | "
            f"{row['safety_termination_gate']} | "
            f"{row['strict_joint_promotion_gate']} |"
        )
    if (
        payload["decision"][
            "new_framework_plus_decentralized_vs_pibt_off_control"
        ]
        == "PASS"
    ):
        control_decision = (
            "- It also beats the matched PIBT-off runtime control on completion "
            "and deadlock behavior. The control completed "
            f"{control['complete_raw_bag_count'][0]:,}/{FULL_SIZE_BAGS:,} bags "
            f"with {control['unresolved_deadlock_count'][0]} unresolved "
            "deadlocks before the event limit."
        )
    else:
        control_decision = (
            "- The sealed evidence does not establish a completion/deadlock "
            "advantage over the matched PIBT-off runtime control."
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- The new event framework plus bounded-local decentralized "
            "coordination beats the parsed historical HCA* comparator on the "
            "matched raw-entry denominator.",
            "- It does not strictly beat frozen v2-safe: F1 and F2 miss by only "
            "about 2.97 s and 1.13 s per raw bag, respectively.",
            control_decision,
            "- The PIBT-off control is event-limit censored, so its TTH is not "
            "comparable. The five repeats establish deterministic reproduction, "
            "not five statistically independent trials.",
            "- The strict joint promotion gate remains FAIL and G4J remains "
            "CLOSED. Phase-K remains UNKNOWN_NOT_COMPUTABLE and Phase-L remains "
            "BLOCKED_NOT_RUN.",
            "- HCA* remains parsed historical evidence rather than a fresh "
            "same-machine rerun, so this is not a final paper-superiority claim.",
            "",
            "## Evidence bindings",
            "",
            f"- Protected input SHA256: `{input_evidence['file_sha256']}`",
            f"- Sealed Phase-J ledger SHA256: `{sealed['file_sha256']}`",
            "- Legacy denominator table SHA256: "
            f"`{payload['legacy_comparator_evidence']['table_file_sha256']}`",
            "- Sealed Phase-J candidate bundle SHA256: "
            f"`{sealed['candidate_bundle_file_sha256']}`",
            "- Preserved formal source bundle SHA256: "
            f"`{sealed['formal_source_bundle_sha256']}`",
            f"- Reconciliation SHA256: `{payload['reconciliation_sha256']}`",
            "",
            "The old 41.5-minute observations remain valid. Only their direct "
            "comparison against 4.124/5.765-minute legacy targets and the "
            "derived HCA blocker are superseded.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def rendered_outputs(
    payload: Mapping[str, Any],
) -> dict[Path, bytes]:
    return {
        POLICY_OUTPUT_PATH: (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
        TABLE_OUTPUT_PATH: _table_bytes(payload),
        REPORT_OUTPUT_PATH: _report_bytes(payload),
    }


def write_outputs(root: Path = ROOT) -> tuple[Path, ...]:
    payload = build_reconciliation(root)
    written: list[Path] = []
    for relative_path, content in rendered_outputs(payload).items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        written.append(path)
    return tuple(written)


def validate_committed_outputs(root: Path = ROOT) -> list[str]:
    payload = build_reconciliation(root)
    failures: list[str] = []
    for relative_path, expected in rendered_outputs(payload).items():
        path = root / relative_path
        if not path.is_file():
            failures.append(f"missing reconciliation output: {relative_path}")
        elif path.read_bytes() != expected:
            failures.append(f"stale reconciliation output: {relative_path}")
    return failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile G4IRSF12 raw-entry performance denominators."
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.write:
        paths = write_outputs(ROOT)
        print(
            json.dumps(
                {"status": STATUS, "written": [str(path) for path in paths]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.check:
        failures = validate_committed_outputs(ROOT)
        if failures:
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print(json.dumps({"status": STATUS, "outputs": "CURRENT"}, indent=2))
        return 0
    print(
        json.dumps(
            build_reconciliation(ROOT),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
