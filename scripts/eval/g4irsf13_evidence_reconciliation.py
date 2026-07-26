"""Freeze the G4IRSF13 control and reconcile append-only G4IRSF12 evidence.

This module deliberately treats the G4IRSF12 execution ledger as immutable.
It consumes the append-only denominator reconciliation, records which older
status documents are stale, and publishes a single G4IRSF13 authority layer.
No simulator execution is performed here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval import g4irsf12_denominator_reconciliation as g12_denominator  # noqa: E402
from scripts.eval import g4irsf12_reproducible_harness as g12_harness  # noqa: E402

START_BRANCH = "codex/czr005-rewrite"
START_COMMIT = "f05e5432c5faa85d8b11d2d153e7da96f340d34c"
START_UPSTREAM = "origin/codex/czr005-rewrite"

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_SHA256 = "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"

DENOMINATOR_POLICY = Path(
    "artifacts/policies/g4irsf12_denominator_reconciliation.json"
)
SEALED_FULL_TABLE = Path("outputs/tables/g4irsf12_original_scale_full_ab.csv")
SEALED_CANDIDATE_BUNDLE = Path(
    "artifacts/policies/g4irsf12_original_scale_candidate_bundle.json"
)

RECONCILIATION_REPORT = Path(
    "outputs/reports/g4irsf13_authoritative_evidence_reconciliation.md"
)
FRESHNESS_TABLE = Path("outputs/tables/g4irsf13_artifact_freshness_audit.csv")
BASELINE_MANIFEST = Path(
    "artifacts/gates/g4irsf13_baseline_freeze_manifest.json"
)
F2_POLICY = Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json")
ANCESTRY_REPORT = Path(
    "outputs/reports/g4irsf13_repository_ancestry_boundary.md"
)

EXPECTED_F2_MEAN_MINUTES = 41.514218717973414
EXPECTED_F2_SENSITIVE_MINUTES = 4.143217183651398
EXPECTED_V2_TARGET_MINUTES = 41.49530698780892
EXPECTED_HCA_TARGET_MINUTES = 43.13593828041816
EXPECTED_F2_RESULT_SHA256 = (
    "23c52e4412eb2359f907ed145f3cc0b6de8392af1dff184b8324b19b0b7c05f0"
)
EXPECTED_F2_CONFIG_SHA256 = (
    "60c91e937f3c8f14ff4a80f685ec3294da6e22196cdf254eea998acb677becf1"
)
EXPECTED_F2_BINARY_SHA256 = (
    "82f15f08a8cff0e887447f017f0aa03fffabe9bfb3a79a563b16d779219d8222"
)
EXPECTED_F2_SOURCE_BUNDLE_SHA256 = (
    "eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7"
)
EXPECTED_F2_SOURCE_MANIFEST_SHA256 = (
    "720843eb169dc451d8949c4d6b4d8dec8f3d43a6288492c5d23ef8321a712c3b"
)
EXPECTED_F2_EXECUTOR_SOURCE_SHA256 = (
    "e1b59eecded76f59991a9276f614aea747a573dbaffdf2139cfd9b6096b69971"
)


class EvidenceError(ValueError):
    """Raised when frozen evidence cannot be admitted."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise EvidenceError(f"missing evidence file: {path}")
    return _sha256_bytes(path.read_bytes())


def _semantic_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return _sha256_bytes(normalized.encode("utf-8"))


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceError(f"expected JSON object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _git(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout.strip()


def _close(left: Any, right: float, tolerance: float = 1.0e-9) -> bool:
    try:
        return abs(float(left) - right) <= tolerance
    except (TypeError, ValueError):
        return False


def _strict_bool(value: str) -> bool:
    if value not in {"True", "False"}:
        raise EvidenceError(f"non-canonical boolean in sealed ledger: {value!r}")
    return value == "True"


def _f2_rows(root: Path) -> list[dict[str, str]]:
    rows = [
        row
        for row in _read_csv(root / SEALED_FULL_TABLE)
        if row.get("candidate_id") == "J_F2"
        and row.get("execution_status") == "EXECUTED"
    ]
    if len(rows) != 5:
        raise EvidenceError(f"expected five sealed F2 repeats, got {len(rows)}")
    return rows


def validate_inputs(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    if _file_sha256(root / MAP_PATH) != MAP_RAW_SHA256:
        failures.append("canonical map raw SHA-256 drift")
    if _semantic_sha256(root / MAP_PATH) != MAP_SEMANTIC_SHA256:
        failures.append("canonical map semantic SHA-256 drift")
    if _file_sha256(root / TASK_PATH) != TASK_SHA256:
        failures.append("canonical task SHA-256 drift")

    denominator_failures = g12_denominator.validate_committed_outputs(root)
    failures.extend(
        f"G4IRSF12 denominator reconciliation: {failure}"
        for failure in denominator_failures
    )
    try:
        # This validates every ledger column, row binding, runtime-control echo,
        # protected prefix, and execution provenance before raw values below
        # are frozen into G4IRSF13.
        g12_harness.load_result_ledger(root / SEALED_FULL_TABLE, root=root)
    except Exception as exc:  # noqa: BLE001 - fail closed on inherited evidence
        failures.append(f"sealed Phase-J ledger validation failed: {exc}")

    denominator = _read_object(root / DENOMINATOR_POLICY)
    targets = denominator.get("corrected_targets", {})
    if not _close(
        targets.get("v2_safe_raw_entry_target_minutes"),
        EXPECTED_V2_TARGET_MINUTES,
    ):
        failures.append("corrected v2-safe target drift")
    if not _close(
        targets.get("historical_hca_raw_entry_target_minutes"),
        EXPECTED_HCA_TARGET_MINUTES,
    ):
        failures.append("corrected historical HCA target drift")
    if denominator.get("sealed_execution_evidence_rewritten") is not False:
        failures.append("denominator reconciliation rewrote sealed evidence")
    sealed = denominator.get("sealed_phase_j_evidence", {})
    physical_expectations = (
        (
            SEALED_FULL_TABLE,
            sealed.get("file_sha256"),
            "sealed Phase-J table physical SHA-256",
        ),
        (
            SEALED_CANDIDATE_BUNDLE,
            sealed.get("candidate_bundle_file_sha256"),
            "sealed candidate bundle physical SHA-256",
        ),
    )
    for path, expected, label in physical_expectations:
        if not isinstance(expected, str) or _file_sha256(root / path) != expected:
            failures.append(f"{label} drift")
    candidate_bundle = _read_object(root / SEALED_CANDIDATE_BUNDLE)
    if candidate_bundle.get("bundle_sha256") != sealed.get(
        "candidate_bundle_self_sha256"
    ):
        failures.append("sealed candidate bundle self-hash field drift")
    if sealed.get("formal_source_bundle_sha256") != EXPECTED_F2_SOURCE_BUNDLE_SHA256:
        failures.append("sealed formal source bundle hash drift")
    legacy = denominator.get("legacy_comparator_evidence", {})
    legacy_path = root / Path(str(legacy.get("table_path", "")))
    if (
        not legacy_path.is_file()
        or _file_sha256(legacy_path) != legacy.get("table_file_sha256")
    ):
        failures.append("legacy comparator table physical SHA-256 drift")

    try:
        rows = _f2_rows(root)
    except EvidenceError as exc:
        return [*failures, str(exc)]
    expected_repeats = ["1", "2", "3", "4", "5"]
    if sorted(row["repeat_index"] for row in rows) != expected_repeats:
        failures.append("F2 repeat indexes are not exactly 1..5")
    row_bindings: set[str] = set()
    for row in rows:
        if row.get("deterministic_result_sha256") != EXPECTED_F2_RESULT_SHA256:
            failures.append("F2 deterministic result hash drift")
        if row.get("repeat_consistency") != "MATCH":
            failures.append("F2 repeat consistency is not MATCH")
        exact_expectations = {
            "case_config_sha256": EXPECTED_F2_CONFIG_SHA256,
            "binary_sha256": EXPECTED_F2_BINARY_SHA256,
            "loaded_cpp_binary_sha256": EXPECTED_F2_BINARY_SHA256,
            "source_bundle_sha256": EXPECTED_F2_SOURCE_BUNDLE_SHA256,
            "source_path_manifest_sha256": EXPECTED_F2_SOURCE_MANIFEST_SHA256,
            "executor_source_sha256": EXPECTED_F2_EXECUTOR_SOURCE_SHA256,
            "resource_semantics_echo": "R3_java_node_window_compatible",
            "scorer_mode_echo": "S1_frozen_g4e_legal_local_adapter",
            "pibt_mode_echo": "P2",
            "pressure_mode_echo": "off",
            "admission_mode_echo": "off",
            "framework_mode_echo": "event_loop_one_step",
            "pibt_max_depth_echo": "2",
            "primary_denominator": "original_entry_time_tth",
        }
        for name, expected in exact_expectations.items():
            if row.get(name) != expected:
                failures.append(f"F2 {name} drift")
        binding = row.get("evidence_row_binding_sha256", "")
        if len(binding) != 64:
            failures.append("F2 evidence row binding is missing or malformed")
        row_bindings.add(binding)
        if not _close(row.get("original_entry_mean_minutes"), EXPECTED_F2_MEAN_MINUTES):
            failures.append("F2 original-entry mean drift")
        if not _close(
            row.get("java_release_mean_minutes"),
            EXPECTED_F2_SENSITIVE_MINUTES,
        ):
            failures.append("F2 decision-sensitive mean drift")
        integer_expectations = {
            "complete_raw_bag_count": "28506",
            "completed_segment_count": "43603",
            "failed_segment_count": "0",
            "conflict_count": "0",
            "unsafe_entry_count": "0",
            "runtime_full_astar_calls": "0",
            "global_reservation_scan_count": "0",
            "future_routes_stored": "0",
            "unresolved_deadlock_count": "0",
            "reservation_depth": "1",
            "max_edges_selected_per_bag_per_decision": "1",
        }
        for name, expected in integer_expectations.items():
            if row.get(name) != expected:
                failures.append(f"F2 {name} drift")
        for name in ("event_limit_reached", "time_limit_reached"):
            try:
                observed = _strict_bool(row.get(name, ""))
            except EvidenceError as exc:
                failures.append(str(exc))
            else:
                if observed:
                    failures.append(f"F2 {name} unexpectedly true")
        if row.get("map_raw_sha256") != MAP_RAW_SHA256:
            failures.append("F2 map binding drift")
        if row.get("source_raw_sha256") != TASK_SHA256:
            failures.append("F2 task binding drift")
    if len(row_bindings) != 5:
        failures.append("F2 repeat row bindings are not unique")
    return sorted(set(failures))


def _artifact_rows(root: Path) -> list[dict[str, str]]:
    definitions = (
        (
            "outputs/reports/g4irsf12_resource_semantics_audit.md",
            "resource_semantics",
            "STATIC_EVIDENCE_COMPLETE_RUNTIME_AB_NOT_EXECUTED",
            "R3_EXECUTED_IN_F1_F2",
            "SUPERSEDED_STATUS_RETAINED_AS_HISTORY",
            "The static report predates the sealed R3 full executions.",
        ),
        (
            "outputs/reports/g4irsf12_bounded_local_pibt_design.md",
            "bounded_local_pibt",
            "DESIGN_ONLY_RUNTIME_METRICS_NOT_CLAIMED",
            "P2_FULL_AND_P0_CENSORED_CONTROL_EXECUTED",
            "SUPERSEDED_STATUS_RETAINED_AS_HISTORY",
            "The design report predates P2 full runs and the P0 negative control.",
        ),
        (
            "outputs/reports/g4irsf12_v3_training_status.json",
            "v3_status",
            "ALL_PRETRAINING_GATES_MISSING",
            "TRAINING_STILL_NOT_RUN_BUT_PREREQUISITE_STATUS_PARTLY_STALE",
            "PARTIALLY_SUPERSEDED",
            "The no-model conclusion remains current; R3/P2/8192 evidence is no longer missing.",
        ),
        (
            SEALED_CANDIDATE_BUNDLE.as_posix(),
            "candidate_bundle",
            "PRE_DENOMINATOR_TARGETS_AND_GATES",
            "EXECUTION_PROVENANCE_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "Execution hashes remain sealed; G4IRSF12 reconciliation supersedes targets.",
        ),
        (
            SEALED_FULL_TABLE.as_posix(),
            "full_execution_ledger",
            "SEALED_EXECUTION_WITH_PRE_RECONCILIATION_GATES",
            "EXECUTION_COUNTERS_AND_PROVENANCE_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "Rows stay immutable; corrected comparisons are append-only.",
        ),
        (
            DENOMINATOR_POLICY.as_posix(),
            "denominator_reconciliation",
            "VERIFIED_DENOMINATOR_MISMATCH",
            "AUTHORITATIVE_G4IRSF13_INPUT",
            "CURRENT",
            "This is the sole corrected comparator source inherited by G4IRSF13.",
        ),
        (
            "outputs/reports/g4irsf12_original_entry_denominator_report.md",
            "original_entry_denominator_report",
            "PRE_APPEND_ONLY_RECONCILIATION_TARGET_INTERPRETATION",
            "HISTORICAL_CONTEXT_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "The append-only denominator reconciliation is newer and authoritative.",
        ),
        (
            "artifacts/configs/g4irsf12_reproducible_harness_manifest.json",
            "reproducible_harness_manifest",
            "PRE_RECONCILIATION_TARGET_BINDING",
            "HARNESS_PROTOCOL_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "Runtime protocol remains useful; old comparator bindings do not.",
        ),
        (
            "outputs/reports/g4irsf12_original_scale_full_ab.md",
            "original_scale_report",
            "PRE_RECONCILIATION_GATE_NARRATIVE",
            "SEALED_EXECUTION_CONTEXT_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "The execution rows are sealed; the displayed targets are obsolete.",
        ),
        (
            "outputs/reports/g4irsf12_promotion_gate.md",
            "promotion_gate_report",
            "PRE_RECONCILIATION_GATE_NARRATIVE",
            "HISTORICAL_GATE_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "G4IRSF13 recomputes promotion only from corrected raw-entry controls.",
        ),
        (
            "outputs/reports/g4irsf12_plain_language_summary_zh.md",
            "plain_language_summary",
            "PRE_RECONCILIATION_PERFORMANCE_SUMMARY",
            "HISTORICAL_CONTEXT_ONLY",
            "PERFORMANCE_FIELDS_SUPERSEDED",
            "The later denominator reconciliation controls numerical claims.",
        ),
        (
            "outputs/reports/g4irsf12_prior_evidence_reconciliation.md",
            "prior_evidence_reconciliation",
            "PRE_FULL_RUNTIME_STATUS_RECONCILIATION",
            "HISTORICAL_EVIDENCE_LAYER",
            "PARTIALLY_SUPERSEDED",
            "Its source boundaries remain useful; later R3/P2 execution changes status.",
        ),
    )
    rows: list[dict[str, str]] = []
    for path_text, domain, observed, authority, freshness, rationale in definitions:
        path = root / Path(path_text)
        rows.append(
            {
                "artifact": Path(path_text).as_posix(),
                "evidence_domain": domain,
                "observed_status": observed,
                "g4irsf13_authoritative_status": authority,
                "freshness": freshness,
                "file_sha256": _file_sha256(path),
                "rationale": rationale,
            }
        )
    return rows


def build_payloads(root: Path = ROOT) -> dict[Path, bytes]:
    failures = validate_inputs(root)
    if failures:
        raise EvidenceError(" | ".join(failures))

    denominator = _read_object(root / DENOMINATOR_POLICY)
    rows = _f2_rows(root)
    representative = rows[0]
    targets = denominator["corrected_targets"]
    evidence_paths = (
        DENOMINATOR_POLICY,
        SEALED_FULL_TABLE,
        SEALED_CANDIDATE_BUNDLE,
    )
    evidence_hashes = {
        path.as_posix(): _file_sha256(root / path) for path in evidence_paths
    }

    f2_policy: dict[str, Any] = {
        "schema": "czr005.g4irsf13.f2_frozen_baseline.v1",
        "candidate_id": "G4IRSF13_F2_FROZEN",
        "inherited_candidate_id": "J_F2",
        "configuration": {
            "framework": "event_loop_one_step",
            "resource": "R3_java_node_window_compatible",
            "scorer": "S1_frozen_g4e_legal_local_adapter",
            "pibt": "P2",
            "control": "C0",
            "pressure_mode": "off",
            "admission_mode": "off",
            "reservation_depth": 1,
        },
        "protected_inputs": {
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": MAP_RAW_SHA256,
            "map_semantic_sha256": MAP_SEMANTIC_SHA256,
            "task_path": TASK_PATH.as_posix(),
            "task_sha256": TASK_SHA256,
            "raw_bag_count": 28506,
            "segment_count": 43603,
        },
        "metrics": {
            "original_entry_mean_minutes": EXPECTED_F2_MEAN_MINUTES,
            "scheduled_pre_release_offset_minutes": targets[
                "scheduled_pre_release_offset_minutes"
            ],
            "decision_sensitive_mean_minutes": EXPECTED_F2_SENSITIVE_MINUTES,
            "source_wait_mean_minutes": float(
                representative["source_wait_mean_minutes"]
            ),
            "network_time_mean_minutes": float(
                representative["network_time_mean_minutes"]
            ),
            "original_entry_p95_seconds": float(
                representative["original_entry_p95_seconds"]
            ),
            "original_entry_p99_seconds": float(
                representative["original_entry_p99_seconds"]
            ),
            "delta_vs_v2_safe_seconds": (
                EXPECTED_F2_MEAN_MINUTES - EXPECTED_V2_TARGET_MINUTES
            )
            * 60.0,
        },
        "hard_gates": {
            "complete_raw_bags": 28506,
            "completed_segments": 43603,
            "failed_segments": 0,
            "conflicts": 0,
            "unsafe_entries": 0,
            "runtime_full_astar_calls": 0,
            "global_reservation_scans": 0,
            "future_routes_stored": 0,
            "unresolved_deadlocks": 0,
            "event_limit_reached": False,
            "time_limit_reached": False,
            "max_edges_selected_per_bag_per_decision": 1,
        },
        "pibt_counters": {
            "applicability": int(representative["pibt_applicability_count"]),
            "attempt": int(representative["pibt_attempt_count"]),
            "prepare": int(representative["pibt_prepare_count"]),
            "validate": int(representative["pibt_validate_count"]),
            "commit": int(representative["pibt_commit_count"]),
            "rollback": int(representative["pibt_rollback_count"]),
            "backtrack": int(representative["pibt_backtrack_count"]),
            "handoff": int(representative["pibt_handoff_count"]),
        },
        "provenance": {
            "phase_start_commit": START_COMMIT,
            "case_config_sha256": representative["case_config_sha256"],
            "binary_sha256": representative["binary_sha256"],
            "source_bundle_sha256": representative["source_bundle_sha256"],
            "source_path_manifest_sha256": representative[
                "source_path_manifest_sha256"
            ],
            "executor_id": representative["executor_id"],
            "executor_source_sha256": representative["executor_source_sha256"],
            "deterministic_result_sha256": EXPECTED_F2_RESULT_SHA256,
            "repeat_count": 5,
            "repeat_indexes": [1, 2, 3, 4, 5],
            "evidence_row_binding_sha256": [
                row["evidence_row_binding_sha256"] for row in rows
            ],
            "evidence_files": evidence_hashes,
        },
        "claim_boundary": (
            "Frozen control only. It beats corrected historical HCA but remains "
            "1.13470381 s/bag slower than frozen v2-safe."
        ),
    }
    f2_policy["policy_sha256"] = _canonical_sha256(f2_policy)

    baseline_manifest: dict[str, Any] = {
        "schema": "czr005.g4irsf13.baseline_freeze_manifest.v1",
        "phase": "G4IRSF13-A",
        "status": "PASS",
        "phase_start": {
            "branch": START_BRANCH,
            "commit": START_COMMIT,
            "upstream": START_UPSTREAM,
        },
        "authoritative_report": RECONCILIATION_REPORT.as_posix(),
        "frozen_control": F2_POLICY.as_posix(),
        "frozen_control_policy_sha256": f2_policy["policy_sha256"],
        "corrected_targets": targets,
        "protected_inputs": f2_policy["protected_inputs"],
        "evidence_files": evidence_hashes,
        "sealed_artifacts_rewritten": False,
        "supersession_is_field_scoped": True,
        "g4j_status": "CLOSED",
        "phase_k_status": "UNKNOWN",
        "phase_l_status": "NOT_RUN",
    }
    baseline_manifest["manifest_sha256"] = _canonical_sha256(baseline_manifest)

    freshness_rows = _artifact_rows(root)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "artifact",
            "evidence_domain",
            "observed_status",
            "g4irsf13_authoritative_status",
            "freshness",
            "file_sha256",
            "rationale",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(freshness_rows)

    local_main_code, local_main = _git(root, "rev-parse", "main")
    remote_main_code, remote_main = _git(root, "rev-parse", "origin/main")
    local_base_code, local_base = _git(root, "merge-base", "main", START_COMMIT)
    remote_base_code, remote_base = _git(
        root, "merge-base", "origin/main", START_COMMIT
    )
    ancestry_text = f"""# G4IRSF13 Repository Ancestry Boundary

Status: `RECORDED_NON_BLOCKING_BOUNDARY`.

- Scientific branch: `{START_BRANCH}` at phase start `{START_COMMIT}`.
- Upstream scientific branch: `{START_UPSTREAM}` at the same phase-start SHA.
- Local `main`: `{local_main if local_main_code == 0 else "UNRESOLVED"}`.
- Local-main merge base: `{local_base if local_base_code == 0 else "NONE"}`.
- `origin/main`: `{remote_main if remote_main_code == 0 else "UNRESOLVED"}`.
- Origin-main merge base: `{remote_base if remote_base_code == 0 else "NONE"}`.

The live audit differs slightly from the planning assumption: the local
`main` ref shares history with the scientific branch, while `origin/main`
has no common ancestor with the phase-start commit. The remote boundary is
the publishing constraint. G4IRSF13 will not force-push, merge unrelated
histories, or rewrite the scientific history. This boundary does not block
the algorithm work; any cross-history pull request requires an explicit
review-base decision.
"""

    report_text = f"""# G4IRSF13 Authoritative Evidence Reconciliation

Status: `PASS_BASELINE_FROZEN`.

This report is the single G4IRSF13 authority layer. It does not rewrite any
G4IRSF12 sealed artifact. Older documents remain historical inputs, with
field-scoped supersession recorded in
`{FRESHNESS_TABLE.as_posix()}`.

## Corrected baseline

| Candidate | Configuration | Original-entry mean | Decision-sensitive mean | v2-safe delta | Hard gates |
| --- | --- | ---: | ---: | ---: | --- |
| F2 frozen | R3/S1/P2/C0 | {EXPECTED_F2_MEAN_MINUTES:.12f} min | {EXPECTED_F2_SENSITIVE_MINUTES:.12f} min | +{(EXPECTED_F2_MEAN_MINUTES - EXPECTED_V2_TARGET_MINUTES) * 60.0:.6f} s/bag | PASS |

The corrected raw-entry controls are:

- frozen v2-safe: `{EXPECTED_V2_TARGET_MINUTES:.12f} min`;
- parsed historical HCA: `{EXPECTED_HCA_TARGET_MINUTES:.12f} min`.

F2 therefore beats the corrected historical HCA control, but it does not
beat frozen v2-safe. The old `4.124305453` and `5.764936746` values are
pass-time-anchored control values and must not be compared directly with the
41-minute raw-entry candidate values.

## Reconciled stale statements

1. R3 is no longer `NOT_RUN`: five full F1 repeats and five full F2 repeats
   executed with the R3 runtime echo.
2. Bounded-local P2 integration is no longer merely a design claim: F1/F2
   completed full 1x, while the P0 control retained a censored deadlock
   signature. P0 survivor TTH remains non-comparable.
3. The G4IRSF12 v3 status remains correct that no model was trained, but its
   blanket `MISSING` prerequisite statuses are stale for R3, P2, and 8192.
4. The sealed candidate bundle and full table retain valid execution
   provenance; only their pre-reconciliation performance targets, gates, and
   derived blockers are superseded.

## Claim boundary

F2 is frozen as a control, not silently edited. G4J remains `CLOSED`, phase K
remains `UNKNOWN`, and phase L remains `NOT_RUN` until a new candidate
strictly beats v2-safe, demonstrates independent v3 contribution, passes an
informative fault A/B, and satisfies every original-1x hard gate.
"""

    return {
        F2_POLICY: (
            json.dumps(f2_policy, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8"),
        BASELINE_MANIFEST: (
            json.dumps(
                baseline_manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
        FRESHNESS_TABLE: buffer.getvalue().encode("utf-8-sig"),
        ANCESTRY_REPORT: ancestry_text.encode("utf-8"),
        RECONCILIATION_REPORT: report_text.encode("utf-8"),
    }


def write_outputs(root: Path = ROOT) -> tuple[Path, ...]:
    payloads = build_payloads(root)
    written: list[Path] = []
    for relative, payload in payloads.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written.append(path)
    return tuple(written)


def validate_committed_outputs(root: Path = ROOT) -> list[str]:
    failures = validate_inputs(root)
    for path in (
        RECONCILIATION_REPORT,
        FRESHNESS_TABLE,
        BASELINE_MANIFEST,
        F2_POLICY,
        ANCESTRY_REPORT,
    ):
        if not (root / path).is_file():
            failures.append(f"missing committed output: {path.as_posix()}")
    if failures:
        return sorted(set(failures))

    expected_payloads = build_payloads(root)
    for relative, expected in expected_payloads.items():
        observed = (root / relative).read_bytes()
        if observed != expected:
            failures.append(
                f"committed output differs from deterministic render: {relative.as_posix()}"
            )

    policy = _read_object(root / F2_POLICY)
    policy_copy = dict(policy)
    observed_policy_sha = policy_copy.pop("policy_sha256", "")
    if observed_policy_sha != _canonical_sha256(policy_copy):
        failures.append("F2 policy self-hash mismatch")
    if policy.get("candidate_id") != "G4IRSF13_F2_FROZEN":
        failures.append("unexpected frozen control ID")

    manifest = _read_object(root / BASELINE_MANIFEST)
    manifest_copy = dict(manifest)
    observed_manifest_sha = manifest_copy.pop("manifest_sha256", "")
    if observed_manifest_sha != _canonical_sha256(manifest_copy):
        failures.append("baseline manifest self-hash mismatch")
    if manifest.get("frozen_control_policy_sha256") != policy.get("policy_sha256"):
        failures.append("manifest-to-policy hash binding mismatch")
    if manifest.get("sealed_artifacts_rewritten") is not False:
        failures.append("manifest claims sealed artifacts were rewritten")

    rows = _read_csv(root / FRESHNESS_TABLE)
    if len(rows) != 12:
        failures.append("freshness audit must contain exactly twelve source artifacts")
    if sum(row["freshness"] == "CURRENT" for row in rows) != 1:
        failures.append("freshness audit must identify one current inherited authority")
    return sorted(set(failures))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--validate-committed", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    if args.write:
        paths = write_outputs(root)
        result: Mapping[str, Any] = {
            "status": "PASS",
            "written": [path.resolve().as_posix() for path in paths],
        }
    elif args.validate_committed:
        failures = validate_committed_outputs(root)
        result = {"status": "PASS" if not failures else "FAIL", "failures": failures}
    else:
        failures = validate_inputs(root)
        result = {"status": "PASS" if not failures else "FAIL", "failures": failures}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
