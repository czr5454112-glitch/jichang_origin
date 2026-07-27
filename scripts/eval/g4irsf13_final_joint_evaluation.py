"""Run the hash-bound G4IRSF13 original-scale joint decision.

Only two candidates are authorized for fresh full-1x execution:

* H0: frozen F2, R3/S1/P2/C0/Q0;
* H1: the no-new-learning Q1 thesis-local priority projection.

H1 is selected by an explicit interpretability tie-break after Q0/Q1/Q3 and
P1/P2/P3 were outcome-identical at 8192.  H2 and H3 fail closed because the
v3 offline gate failed.  Every admitted candidate is executed five times with
the same deterministic request.  The repeats prove reproducibility; they are
not treated as independent statistical samples.

The committed CSV contains aggregate rows, repeat bindings, and real-input
source/goal/hour/continuous-block/EBS/contention/storage slices.  Large runtime
payloads are not committed.  Compact repeat evidence is retained in the local,
gitignored, hash-keyed archive.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
from scripts.eval import g4irsf13_cde_experiments as cde  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    assert_canonical_map,
    canonical_graph_records,
)


SCHEMA = "czr005.g4irsf13.original_scale_joint.v1"
ARCHIVE_SCHEMA = "czr005.g4irsf13.original_scale_repeat_archive.v1"
BUNDLE_SCHEMA = "czr005.g4irsf13.final_candidate_bundle.v1"
LOCAL_ARCHIVE = Path(".local_archives/g4irsf13_final_joint")
TABLE_PATH = Path("outputs/tables/g4irsf13_original_scale_joint_ab.csv")
REPORT_PATH = Path(
    "outputs/reports/g4irsf13_original_scale_joint_decision.md"
)
BUNDLE_PATH = Path("artifacts/policies/g4irsf13_final_candidate_bundle.json")
PROJECTION_AUDIT_PATH = Path(
    "artifacts/policies/g4irsf13_h1_failed_projection_audit.json"
)
VALIDATOR_FAILURE_AUDIT_PATH = Path(
    "artifacts/policies/g4irsf13_h_projection_validator_failure_audit.json"
)
REPORT_ENCODING_AUDIT_PATH = Path(
    "artifacts/policies/g4irsf13_h_report_encoding_validator_failure_audit.json"
)

FULL_SEGMENTS = 43_603
FULL_RAW_BAGS = 28_506
REPEAT_COUNT = 5
MAX_FULL_FINALISTS = 4
CONTINUOUS_BLOCK_SECONDS = 6 * 60 * 60

# Only measurements derived from host execution time may be excluded from the
# algorithm-equivalence hash.  Every bag field, junction-state field, and all
# safety/PIBT/priority/fault counters remain inside their dedicated hashes.
NONALGORITHM_RUNTIME_FIELDS = frozenset(
    {
        "wall_seconds",
        "runtime_seconds",
        "event_throughput_per_second",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "peak_working_set_bytes",
        "working_set_bytes",
        "peak_rss_bytes",
        "rss_bytes",
    }
)
LEGACY_FAILED_H_RUNNER_SHA256 = (
    "3fb30499416dafd70e56ca1e0a69481960b00ecc676323d86510dec4e6069c1b"
)

# These are the Stage-B reconciled raw-entry controls.  The old
# 4.124305453/5.764936746 values are pass-time anchored and are never used as
# original-entry targets in this runner.
HISTORICAL_HCA_RAW_ENTRY_MINUTES = 43.13593828041816
FROZEN_V2_SAFE_RAW_ENTRY_MINUTES = 41.49530698780892
F1_RAW_ENTRY_MINUTES = 41.544748409137824
F2_RECONCILED_RAW_ENTRY_MINUTES = 41.514218717973414
SCHEDULED_DWELL_MINUTES = 37.37100153432201

EXPECTED_V3_FILE_SHA256 = {
    "artifacts/policies/g4irsf13_v3_candidate_bundle.json": (
        "eb274cab76443a4208ed911afb9d006cfb26fb1807b8a16b6dc9c603e917dac4"
    ),
    "artifacts/datasets/g4irsf13_v3_source_manifest.json": (
        "b30a8dff4dbf8e4f9d987fa9d0bfc28e8a58b9b7fcdc63a20f1fcc5507ce09f5"
    ),
    "artifacts/gates/g4irsf13_v3_pretraining_gate_manifest.json": (
        "f8885e4c93531e766f24f52fc33891010954424787eb14029ed5df4b26f46a01"
    ),
    "artifacts/models/g4irsf13_v3_v5_best_plus_calibrated_risk_head.json": (
        "70a30954dba09c623d9e5710059eee13a3fe85e08f2714725fbbfe1084cc2db9"
    ),
}

SELECTION_EVIDENCE_PATHS = (
    Path("outputs/tables/g4irsf13_priority_ablation.csv"),
    Path("outputs/tables/g4irsf13_scorer_priority_pibt_control_matrix.csv"),
    Path("outputs/tables/g4irsf13_pibt_depth_priority_ablation.csv"),
    Path("outputs/tables/g4irsf13_pibt_dodge_regret_ablation.csv"),
    Path("artifacts/datasets/g4irsf13_pibt_contention_manifest.json"),
)

REFERENCE_EVIDENCE_PATHS = (
    Path("artifacts/gates/g4irsf13_baseline_freeze_manifest.json"),
    Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
    Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json"),
    Path("outputs/tables/g4irsf12_original_scale_full_ab.csv"),
    Path("outputs/tables/g4irsf13_per_bag_delta.csv"),
    Path("outputs/tables/g4irsf13_fault_causal_ab.csv"),
    Path("artifacts/policies/g4irsf13_fault_control_bundle.json"),
)

SOURCE_BUNDLE_PATHS = (
    Path("scripts/eval/g4irsf13_final_joint_evaluation.py"),
    Path("scripts/eval/g4irsf13_cde_experiments.py"),
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("src/czr005/cpp_backend.py"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    Path("cpp/ics_core/runtime/expiring_first_edge_credit.hpp"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
)


class JointEvaluationError(ValueError):
    """Raised when final evidence is missing, stale, or internally invalid."""


@dataclass(frozen=True)
class Finalist:
    candidate_id: str
    role: str
    priority_mode: str
    selection_reason: str

    def controls(self) -> dict[str, Any]:
        candidate = cde.Candidate(
            candidate_id=self.candidate_id,
            family="priority",
            scorer="S1_frozen_g4e_legal_local_adapter",
            pibt="P2",
            control="C0",
            priority=self.priority_mode,
            framework="event_loop_one_step",
            preference="current",
        )
        controls = cde.candidate_runtime_controls(candidate, qbest=None)
        controls["enable_fault_policy"] = True
        return controls


FINALISTS = (
    Finalist(
        "H0_F2_FROZEN",
        "frozen F2 control",
        "Q0",
        "authoritative Stage-B frozen control",
    ),
    Finalist(
        "H1_Q1_THESIS_NO_LEARNING",
        "best no-new-learning candidate",
        "Q1",
        (
            "predeclared interpretable thesis-local priority tie-break after "
            "Q0/Q1/Q3 and P1/P2/P3 were outcome-identical"
        ),
    ),
)

V3_BLOCKER = (
    "V3_OFFLINE_GATE_FAIL:RUNTIME_ELIGIBLE_FALSE:"
    "CLOSED_LOOP_NOT_RUN"
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise JointEvaluationError(f"missing JSON evidence: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JointEvaluationError(f"cannot decode JSON evidence {path}") from exc
    if not isinstance(value, dict):
        raise JointEvaluationError(f"JSON root must be an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise JointEvaluationError(f"missing CSV evidence: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _repository_head(root: Path = ROOT) -> str:
    metadata = root / ".git"
    if metadata.is_file():
        pointer = metadata.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir:"):
            raise JointEvaluationError("invalid gitdir pointer")
        metadata = (metadata.parent / pointer.split(":", 1)[1].strip()).resolve()
    head_path = metadata / "HEAD"
    if not head_path.is_file():
        raise JointEvaluationError("repository HEAD is missing")
    head = head_path.read_text(encoding="ascii").strip()
    if head.startswith("ref:"):
        reference = head.split(":", 1)[1].strip()
        reference_path = metadata / reference
        if reference_path.is_file():
            head = reference_path.read_text(encoding="ascii").strip()
        else:
            packed = metadata / "packed-refs"
            if not packed.is_file():
                raise JointEvaluationError(
                    f"repository HEAD ref is missing: {reference}"
                )
            matches = [
                line.split(" ", 1)[0]
                for line in packed.read_text(
                    encoding="ascii"
                ).splitlines()
                if line and not line.startswith(("#", "^"))
                and line.endswith(f" {reference}")
            ]
            if len(matches) != 1:
                raise JointEvaluationError(
                    f"repository packed HEAD ref drift: {reference}"
                )
            head = matches[0]
    if len(head) != 40:
        raise JointEvaluationError("repository HEAD is not a SHA-1 object ID")
    try:
        int(head, 16)
    except ValueError as exc:
        raise JointEvaluationError(
            "repository HEAD contains non-hex characters"
        ) from exc
    return head.lower()


def _file_bindings(
    paths: Iterable[Path],
    *,
    root: Path = ROOT,
) -> dict[str, str]:
    return {
        path.as_posix(): cde.file_sha256(root / path)
        for path in paths
    }


def _source_bundle(root: Path = ROOT) -> dict[str, Any]:
    rows = [
        {
            "path": path.as_posix(),
            "sha256": cde.file_sha256(root / path),
        }
        for path in SOURCE_BUNDLE_PATHS
    ]
    return {
        "files": rows,
        "bundle_sha256": cde.canonical_sha256(rows),
        "path_manifest_sha256": cde.canonical_sha256(
            [row["path"] for row in rows]
        ),
    }


def algorithm_projection_hashes(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Hash complete algorithm state with an explicit timing-only whitelist."""

    summary = payload.get("summary")
    bags = payload.get("bags")
    junction_state = payload.get("junction_state")
    if not isinstance(summary, Mapping):
        raise JointEvaluationError("algorithm projection lacks summary")
    if not isinstance(bags, list):
        raise JointEvaluationError("algorithm projection lacks bags")
    if not isinstance(junction_state, list):
        raise JointEvaluationError(
            "algorithm projection lacks junction_state"
        )
    algorithm_summary = {
        str(key): value
        for key, value in sorted(summary.items(), key=lambda pair: str(pair[0]))
        if str(key) not in NONALGORITHM_RUNTIME_FIELDS
    }
    nondeterministic_observations = {
        str(key): value
        for key, value in sorted(summary.items(), key=lambda pair: str(pair[0]))
        if str(key) in NONALGORITHM_RUNTIME_FIELDS
    }
    trace_lengths: dict[str, int] = {}
    for name in (
        "events",
        "decisions",
        "decision_trace",
        "hold_attempts",
        "pibt_events",
        "credit_events",
        "fault_events",
    ):
        value = payload.get(name, [])
        if not isinstance(value, list):
            raise JointEvaluationError(
                f"algorithm projection trace {name} is not an array"
            )
        trace_lengths[name] = len(value)
    projection = {
        "bags": bags,
        "junction_state": junction_state,
        "summary": algorithm_summary,
        "trace_context": payload.get("trace_context", {}),
        "trace_lengths": trace_lengths,
        "loaded_cpp_binary_path": payload.get(
            "loaded_cpp_binary_path", ""
        ),
        "loaded_cpp_binary_sha256": payload.get(
            "loaded_cpp_binary_sha256", ""
        ),
    }
    return {
        "runtime_algorithm_sha256": cde.canonical_sha256(projection),
        "bags_sha256": cde.canonical_sha256(bags),
        "junction_state_sha256": cde.canonical_sha256(junction_state),
        "algorithm_summary_sha256": cde.canonical_sha256(
            algorithm_summary
        ),
        "trace_context_sha256": cde.canonical_sha256(
            payload.get("trace_context", {})
        ),
        "trace_lengths": trace_lengths,
        "nondeterministic_observations": nondeterministic_observations,
        "excluded_field_names": sorted(NONALGORITHM_RUNTIME_FIELDS),
    }


def bind_failed_projection_audit(root: Path = ROOT) -> dict[str, Any]:
    """Preserve the first five H1 runs without treating them as reusable."""

    committed_path = root / PROJECTION_AUDIT_PATH
    if committed_path.is_file():
        descriptor = _read_json(committed_path)
        if descriptor.get("status") != "FAILED_PROJECTION_AUDIT":
            raise JointEvaluationError(
                "committed failed-projection audit status drift"
            )
        if descriptor.get("reused_for_final_equivalence") is not False:
            raise JointEvaluationError(
                "failed projection evidence must not be reused"
            )
        return {
            "status": descriptor["status"],
            "path": PROJECTION_AUDIT_PATH.as_posix(),
            "file_sha256": cde.file_sha256(committed_path),
            "legacy_experiment_identity_sha256": descriptor[
                "legacy_experiment_identity_sha256"
            ],
            "reused_for_final_equivalence": False,
        }

    archive_base = (
        root
        / LOCAL_ARCHIVE
        / "H1_Q1_THESIS_NO_LEARNING"
    )
    if not archive_base.is_dir():
        raise JointEvaluationError(
            "expected failed H1 projection archive is missing"
        )
    candidates: list[tuple[Path, dict[str, Any], list[Path]]] = []
    for directory in archive_base.iterdir():
        if not directory.is_dir():
            continue
        identity_path = directory / "identity.json"
        repeats_dir = directory / "repeats"
        if not identity_path.is_file() or not repeats_dir.is_dir():
            continue
        identity = _read_json(identity_path)
        files = identity.get("source_bundle", {}).get("files", [])
        runner_hash = next(
            (
                row.get("sha256")
                for row in files
                if isinstance(row, Mapping)
                and row.get("path")
                == "scripts/eval/g4irsf13_final_joint_evaluation.py"
            ),
            None,
        )
        repeat_paths = sorted(repeats_dir.glob("repeat_*.json"))
        if (
            runner_hash == LEGACY_FAILED_H_RUNNER_SHA256
            and len(repeat_paths) == REPEAT_COUNT
            and not (directory / "complete.json").exists()
        ):
            candidates.append((directory, identity, repeat_paths))
    if len(candidates) != 1:
        raise JointEvaluationError(
            "expected exactly one legacy failed-projection archive, "
            f"found {len(candidates)}"
        )
    directory, identity, repeat_paths = candidates[0]
    repeats = [_read_json(path) for path in repeat_paths]
    if any(
        row.get("gate_status") != "PASS"
        or row.get("execution_status") != "EXECUTED"
        for row in repeats
    ):
        raise JointEvaluationError(
            "legacy failed-projection repeat has a hard-gate failure"
        )

    def section_differences(name: str) -> dict[str, list[Any]]:
        sections = [row.get(name) for row in repeats]
        if not all(isinstance(value, Mapping) for value in sections):
            raise JointEvaluationError(
                f"legacy projection section missing: {name}"
            )
        keys = sorted(
            {
                str(key)
                for section in sections
                for key in section
            }
        )
        differences: dict[str, list[Any]] = {}
        for key in keys:
            values = [section.get(key) for section in sections]
            if len({cde.canonical_sha256(value) for value in values}) > 1:
                differences[key] = values
        return differences

    metric_differences = section_differences("metrics")
    counter_differences = section_differences("counters")
    summary_differences = section_differences("runtime_summary")
    expected_varying = {
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
    }
    if metric_differences:
        raise JointEvaluationError(
            "legacy projection has primary metric drift"
        )
    if set(counter_differences) - expected_varying:
        raise JointEvaluationError(
            "legacy projection has non-timing CDE counter drift"
        )
    if set(summary_differences) - (
        expected_varying | {"runtime_seconds"}
    ):
        raise JointEvaluationError(
            "legacy projection has archived non-timing summary drift"
        )
    segment_hashes = {
        row["segment_result_sha256"] for row in repeats
    }
    slice_hashes = {row["slice_projection_sha256"] for row in repeats}
    legacy_hashes = {
        row["runtime_deterministic_sha256"] for row in repeats
    }
    if (
        len(segment_hashes) != 1
        or len(slice_hashes) != 1
        or len(legacy_hashes) == 1
    ):
        raise JointEvaluationError(
            "legacy projection failure signature drift"
        )
    descriptor = {
        "schema": "czr005.g4irsf13.failed_projection_audit.v1",
        "status": "FAILED_PROJECTION_AUDIT",
        "candidate_id": "H1_Q1_THESIS_NO_LEARNING",
        "legacy_experiment_identity_sha256": directory.name,
        "legacy_runner_source_sha256": LEGACY_FAILED_H_RUNNER_SHA256,
        "repeat_count": REPEAT_COUNT,
        "all_runtime_hard_gates_pass": True,
        "reused_for_final_equivalence": False,
        "reason": (
            "the legacy projection omitted event_throughput_per_second from "
            "its timing-only exclusion list and did not retain complete bags, "
            "junction state, or full-summary component hashes; its five runs "
            "cannot be retrospectively admitted as final equivalence evidence"
        ),
        "observed_archived_differences": {
            "metrics": metric_differences,
            "counters": counter_differences,
            "runtime_summary": summary_differences,
        },
        "legacy_runtime_projection_sha256": [
            row["runtime_deterministic_sha256"] for row in repeats
        ],
        "invariant_segment_result_sha256": next(iter(segment_hashes)),
        "invariant_slice_projection_sha256": next(iter(slice_hashes)),
        "repeat_bindings": [
            {
                "repeat_index": int(row["repeat_index"]),
                "local_archive_relative_path": path.relative_to(root).as_posix(),
                "file_sha256": cde.file_sha256(path),
            }
            for row, path in zip(repeats, repeat_paths)
        ],
        "replacement_protocol": {
            "nonalgorithm_runtime_fields": sorted(
                NONALGORITHM_RUNTIME_FIELDS
            ),
            "complete_bags_hash_required": True,
            "junction_state_hash_required": True,
            "full_algorithm_summary_hash_required": True,
            "new_source_identity_required": True,
        },
        "legacy_identity_file_sha256": cde.file_sha256(
            directory / "identity.json"
        ),
    }
    cde.atomic_write_json(committed_path, descriptor)
    return {
        "status": descriptor["status"],
        "path": PROJECTION_AUDIT_PATH.as_posix(),
        "file_sha256": cde.file_sha256(committed_path),
        "legacy_experiment_identity_sha256": directory.name,
        "reused_for_final_equivalence": False,
    }


def bind_projection_validator_failure_audit(
    root: Path = ROOT,
) -> dict[str, Any]:
    path = root / VALIDATOR_FAILURE_AUDIT_PATH
    descriptor = _read_json(path)
    if (
        descriptor.get("status") != "PROJECTION_VALIDATOR_FAILURE"
        or descriptor.get("reused_for_final_equivalence") is not False
        or descriptor.get("total_repeat_count") != 10
        or descriptor.get("all_runtime_hard_gates_pass") is not True
    ):
        raise JointEvaluationError(
            "projection-validator failure audit drift"
        )
    return {
        "status": descriptor["status"],
        "path": VALIDATOR_FAILURE_AUDIT_PATH.as_posix(),
        "file_sha256": cde.file_sha256(path),
        "reused_for_final_equivalence": False,
        "total_repeat_count": 10,
    }


def bind_report_encoding_validator_failure_audit(
    root: Path = ROOT,
) -> dict[str, Any]:
    path = root / REPORT_ENCODING_AUDIT_PATH
    descriptor = _read_json(path)
    if (
        descriptor.get("status") != "REPORT_ENCODING_VALIDATOR_FAILURE"
        or descriptor.get("reused_for_final_equivalence") is not False
        or descriptor.get("total_repeat_count") != 10
        or descriptor.get("all_runtime_hard_gates_pass") is not True
    ):
        raise JointEvaluationError(
            "report-encoding failure audit drift"
        )
    return {
        "status": descriptor["status"],
        "path": REPORT_ENCODING_AUDIT_PATH.as_posix(),
        "file_sha256": cde.file_sha256(path),
        "reused_for_final_equivalence": False,
        "total_repeat_count": 10,
    }


def validate_v3_fail_closed(root: Path = ROOT) -> dict[str, Any]:
    observed = _file_bindings(
        [Path(path) for path in EXPECTED_V3_FILE_SHA256],
        root=root,
    )
    for path, expected in EXPECTED_V3_FILE_SHA256.items():
        if observed[path] != expected:
            raise JointEvaluationError(
                f"v3 evidence drift: {path}={observed[path]}, expected={expected}"
            )
    bundle_path = root / "artifacts/policies/g4irsf13_v3_candidate_bundle.json"
    bundle = _read_json(bundle_path)
    bundle_projection = dict(bundle)
    expected_bundle_self_hash = bundle_projection.pop("bundle_sha256", None)
    if expected_bundle_self_hash != cde.canonical_sha256(bundle_projection):
        raise JointEvaluationError("v3 candidate bundle self-hash drift")

    bound_descriptors = {
        "source_manifest": (
            "artifacts/datasets/g4irsf13_v3_source_manifest.json",
            bundle.get("source_manifest"),
        ),
        "pretraining_gate": (
            "artifacts/gates/g4irsf13_v3_pretraining_gate_manifest.json",
            bundle.get("pretraining_gate"),
        ),
        "v5_model": (
            (
                "artifacts/models/"
                "g4irsf13_v3_v5_best_plus_calibrated_risk_head.json"
            ),
            (
                bundle.get("model_artifacts", {}).get(
                    "V5_best_plus_calibrated_risk_head"
                )
                if isinstance(bundle.get("model_artifacts"), Mapping)
                else None
            ),
        ),
    }
    for label, (path, descriptor) in bound_descriptors.items():
        if not isinstance(descriptor, Mapping):
            raise JointEvaluationError(
                f"v3 bundle descriptor missing: {label}"
            )
        if (
            descriptor.get("path") != path
            or descriptor.get("sha256") != observed[path]
            or int(descriptor.get("size_bytes", -1))
            != (root / path).stat().st_size
        ):
            raise JointEvaluationError(
                f"v3 bundle descriptor drift: {label}"
            )
    expected_fields = {
        "status": "OFFLINE_LEVEL_A_FAIL_CLOSED_LOOP_NOT_RUN",
        "offline_gate_status": "FAIL",
        "runtime_eligible": False,
        "closed_loop_status": "NOT_RUN",
    }
    for field, expected in expected_fields.items():
        if bundle.get(field) != expected:
            raise JointEvaluationError(
                f"v3 dependency field drift: {field}={bundle.get(field)!r}"
            )
    return {
        "status": "FAIL_CLOSED",
        "blocker": V3_BLOCKER,
        "fields": expected_fields,
        "file_bindings": observed,
        "candidate_bundle_self_sha256": expected_bundle_self_hash,
        "recommended_offline_candidate": bundle.get(
            "recommended_offline_candidate", ""
        ),
        "selected_offline_candidate": bundle.get(
            "selected_offline_candidate", ""
        ),
    }


def _matched_numeric_rows(
    rows: Sequence[Mapping[str, str]],
    candidate_ids: Sequence[str],
    *,
    tier: str,
) -> list[Mapping[str, str]]:
    selected: list[Mapping[str, str]] = []
    for candidate_id in candidate_ids:
        matches = [
            row
            for row in rows
            if row.get("candidate_id") == candidate_id
            and row.get("tier") == tier
        ]
        if len(matches) != 1:
            raise JointEvaluationError(
                f"expected one {candidate_id}/{tier} selection row"
            )
        row = matches[0]
        if (
            row.get("execution_status") not in {"EXECUTED", "CACHED"}
            or row.get("gate_status") != "PASS"
        ):
            raise JointEvaluationError(
                f"{candidate_id}/{tier} is not complete hard-gate evidence"
            )
        selected.append(row)
    return selected


def validate_h1_tie_break(root: Path = ROOT) -> dict[str, Any]:
    priority_path = root / SELECTION_EVIDENCE_PATHS[0]
    matrix_path = root / SELECTION_EVIDENCE_PATHS[1]
    depth_path = root / SELECTION_EVIDENCE_PATHS[2]
    priority = _read_csv(priority_path)
    matrix = _read_csv(matrix_path)
    depth = _read_csv(depth_path)
    ladder_rows = [
        *_matched_numeric_rows(
            priority,
            ("C_Q0", "C_Q1", "C_Q3"),
            tier="8192",
        ),
        *_matched_numeric_rows(
            matrix,
            ("D8", "D9"),
            tier="8192",
        ),
    ]
    contention_rows = _matched_numeric_rows(
        depth,
        (
            "E_P1",
            "E_P2",
            "E_P3",
            "E_PRIO0_CURRENT",
            "E_PRIO1_THESIS",
            "E_PRIO2_FAULT_SLACK_AGE_ID",
        ),
        tier="contention_cohort",
    )
    metric_fields = (
        "original_entry_mean_minutes",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
        "pibt_applicability_count",
        "pibt_attempt_count",
        "pibt_commit_count",
        "pibt_rollback_count",
        "pibt_backtrack_count",
        "pibt_max_observed_depth",
    )
    for name in metric_fields:
        if len({row.get(name, "") for row in ladder_rows}) != 1:
            raise JointEvaluationError(
                f"8192 finalists are not outcome-identical for {name}"
            )
        if len({row.get(name, "") for row in contention_rows}) != 1:
            raise JointEvaluationError(
                f"matched contention controls differ for {name}"
            )
    q1 = next(
        row for row in ladder_rows if row.get("candidate_id") == "C_Q1"
    )
    if (
        q1.get("scorer") != "S1_frozen_g4e_legal_local_adapter"
        or q1.get("pibt") != "P2"
        or q1.get("control") != "C0"
        or q1.get("resolved_priority") != "Q1"
    ):
        raise JointEvaluationError("Q1 selection configuration drift")
    manifest = _read_json(
        root / "artifacts/datasets/g4irsf13_pibt_contention_manifest.json"
    )
    gate = manifest.get("matched_gate")
    if (
        not isinstance(gate, Mapping)
        or gate.get("status") != "PASS"
        or gate.get("matched_comparison_eligible") is not True
    ):
        raise JointEvaluationError("matched contention gate is not PASS")
    return {
        "status": "PASS_INTERPRETABLE_TIE_BREAK",
        "selected_candidate_id": "H1_Q1_THESIS_NO_LEARNING",
        "selected_priority_mode": "Q1",
        "empirical_superiority_claimed": False,
        "tie_break": (
            "Q1 thesis-local projection is selected for interpretability; "
            "Q0/Q3/P1/P3 are outcome-identical non-selected alternatives"
        ),
        "not_selected_equal_candidates": ["Q0", "Q3", "P1", "P3"],
        "ladder_selection_sha256": q1["selection_sha256"],
        "matched_contention_cohort_sha256": gate["cohort_sha256"],
        "metric_projection_sha256": cde.canonical_sha256(
            [
                {
                    "candidate_id": row["candidate_id"],
                    **{name: row.get(name, "") for name in metric_fields},
                }
                for row in [*ladder_rows, *contention_rows]
            ]
        ),
        "file_bindings": _file_bindings(
            SELECTION_EVIDENCE_PATHS,
            root=root,
        ),
    }


def _contention_task_ids(root: Path = ROOT) -> tuple[set[int], str]:
    path = root / "outputs/tables/g4irsf13_per_bag_delta.csv"
    rows = _read_csv(path)
    task_ids = {
        int(row["task_id"])
        for row in rows
        if row.get("pibt_involvement") == "True"
    }
    if not task_ids:
        raise JointEvaluationError("F2 evidence has no PIBT-involved raw bags")
    return task_ids, cde.file_sha256(path)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JointEvaluationError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise JointEvaluationError(f"{label} must be finite")
    return result


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise JointEvaluationError("cannot take a quantile of an empty slice")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def augment_raw_bags(
    input_rows: Sequence[Mapping[str, Any]],
    runtime_bags: Sequence[Mapping[str, Any]],
    raw_bags: Sequence[Mapping[str, Any]],
    *,
    contention_task_ids: set[int],
) -> list[dict[str, Any]]:
    inputs: dict[int, list[Mapping[str, Any]]] = {}
    for row in input_rows:
        inputs.setdefault(int(row["task_id"]), []).append(row)
    runtime = {
        str(row["segment_id"]): row
        for row in runtime_bags
        if row.get("segment_id") not in (None, "")
    }
    result: list[dict[str, Any]] = []
    for aggregate in raw_bags:
        task_id = int(aggregate["task_id"])
        task_rows = inputs.get(task_id, [])
        if not task_rows:
            raise JointEvaluationError(f"raw bag {task_id} lacks input rows")
        original_starts = {
            int(row.get("original_start", row["start"])) for row in task_rows
        }
        original_goals = {
            int(row.get("original_goal", row["goal"])) for row in task_rows
        }
        entries = {
            _finite(row["original_entry_time"], "original_entry_time")
            for row in task_rows
        }
        if (
            len(original_starts) != 1
            or len(original_goals) != 1
            or len(entries) != 1
        ):
            raise JointEvaluationError(
                f"raw bag {task_id} original identity is not unique"
            )
        segment_rows = [
            runtime[str(row["segment_id"])]
            for row in task_rows
            if str(row["segment_id"]) in runtime
        ]
        entry = next(iter(entries))
        deadlines = [_finite(row["std"], "std") for row in task_rows]
        finish_times = [
            _finite(row["finish_time"], "finish_time")
            for row in segment_rows
            if row.get("completed") is True
        ]
        deadline_miss = (
            len(finish_times) != len(task_rows)
            or any(
                finish > deadline + 1.0e-9
                for finish, deadline in zip(finish_times, deadlines)
            )
        )
        result.append(
            {
                **dict(aggregate),
                "original_start": next(iter(original_starts)),
                "original_goal": next(iter(original_goals)),
                "original_entry_time": entry,
                "clock_hour": int(math.floor(entry / 3600.0)) % 24,
                "continuous_block_index": int(
                    math.floor(entry / CONTINUOUS_BLOCK_SECONDS)
                ),
                "has_ebs_release": any(
                    str(row.get("leg", "")) == "storage_out"
                    for row in task_rows
                ),
                "f2_contention_involved": task_id in contention_task_ids,
                "path_edge_count": sum(
                    int(row.get("decision_count", 0)) for row in segment_rows
                ),
                "edge_travel_time_seconds": sum(
                    _finite(
                        row.get("edge_travel_time_seconds", 0.0),
                        "edge_travel_time_seconds",
                    )
                    for row in segment_rows
                ),
                "loop_detour_time_seconds": sum(
                    _finite(
                        row.get("loop_extra_time_seconds", 0.0),
                        "loop_extra_time_seconds",
                    )
                    for row in segment_rows
                ),
                "loop_count": sum(
                    int(row.get("loop_count", 0)) for row in segment_rows
                ),
                "deadline_miss": deadline_miss,
            }
        )
    return result


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise JointEvaluationError("cannot summarize an empty real-input slice")
    complete = [row for row in rows if row.get("complete") is True]
    comparison_eligible = len(complete) == len(rows)

    def values(name: str) -> list[float]:
        return [
            _finite(row[name], name)
            for row in complete
            if row.get(name) not in (None, "")
        ]

    original = values("original_entry_time_tth_seconds")
    dwell = values("scheduled_pre_release_wait_seconds")
    source = values("source_wait_seconds")
    network = values("network_time_seconds")
    decisions = values("path_edge_count")
    travel = values("edge_travel_time_seconds")
    detour = values("loop_detour_time_seconds")
    if comparison_eligible and len(original) != len(rows):
        raise JointEvaluationError("complete slice lacks primary timing")

    def mean_minutes(data: Sequence[float]) -> float | None:
        return statistics.fmean(data) / 60.0 if comparison_eligible else None

    return {
        "selected_raw_bag_count": len(rows),
        "complete_raw_bag_count": len(complete),
        "completion_rate": len(complete) / len(rows),
        "comparison_eligible": comparison_eligible,
        "original_entry_mean_minutes": mean_minutes(original),
        "original_entry_median_seconds": (
            statistics.median(original) if comparison_eligible else None
        ),
        "original_entry_p95_seconds": (
            _quantile(original, 0.95) if comparison_eligible else None
        ),
        "original_entry_p99_seconds": (
            _quantile(original, 0.99) if comparison_eligible else None
        ),
        "original_entry_max_seconds": (
            max(original) if comparison_eligible else None
        ),
        "scheduled_dwell_mean_minutes": mean_minutes(dwell),
        "source_wait_mean_minutes": mean_minutes(source),
        "network_time_mean_minutes": mean_minutes(network),
        "decision_sensitive_mean_minutes": (
            statistics.fmean(
                [
                    float(row["source_wait_seconds"])
                    + float(row["network_time_seconds"])
                    for row in complete
                ]
            )
            / 60.0
            if comparison_eligible
            else None
        ),
        "path_edge_count_mean": (
            statistics.fmean(decisions) if comparison_eligible else None
        ),
        "edge_travel_time_mean_seconds": (
            statistics.fmean(travel) if comparison_eligible else None
        ),
        "loop_detour_time_mean_seconds": (
            statistics.fmean(detour) if comparison_eligible else None
        ),
        "loop_count": sum(int(row["loop_count"]) for row in rows),
        "deadline_miss_raw_bag_count": sum(
            bool(row["deadline_miss"]) for row in rows
        ),
    }


def build_slice_rows(
    raw_bags: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    hour_counts: dict[int, int] = {}
    for row in raw_bags:
        hour = int(row["clock_hour"])
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
    busy_hour = min(
        hour_counts,
        key=lambda value: (-hour_counts[value], value),
    )
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}

    def add(
        slice_type: str,
        slice_id: str,
        definition: str,
        row: Mapping[str, Any],
    ) -> None:
        groups.setdefault((slice_type, slice_id, definition), []).append(row)

    for row in raw_bags:
        block = int(row["continuous_block_index"])
        block_start = block * CONTINUOUS_BLOCK_SECONDS
        add(
            "continuous_6h_block",
            str(block),
            f"original_entry_time in [{block_start},{block_start + CONTINUOUS_BLOCK_SECONDS})",
            row,
        )
        add(
            "source",
            str(row["original_start"]),
            "protected original_start",
            row,
        )
        add(
            "goal",
            str(row["original_goal"]),
            "protected original_goal",
            row,
        )
        add(
            "clock_hour",
            f"{int(row['clock_hour']):02d}",
            "floor(original_entry_time/3600) modulo 24",
            row,
        )
        add(
            "storage_lifecycle",
            "EBS_SPLIT" if row["has_ebs_release"] else "DIRECT",
            (
                "raw bag has a protected storage_out release from EBS node 52"
                if row["has_ebs_release"]
                else "protected direct raw bag"
            ),
            row,
        )
        if int(row["clock_hour"]) == busy_hour:
            add(
                "busy_hour",
                f"{busy_hour:02d}",
                "highest protected raw-bag count clock hour; ties choose lowest",
                row,
            )
        if row["has_ebs_release"]:
            add(
                "ebs_release",
                "HAS_STORAGE_OUT",
                "protected raw bag includes the scheduled storage_out EBS leg",
                row,
            )
        if row["f2_contention_involved"]:
            add(
                "contention",
                "F2_ACTUAL_PIBT_INVOLVED",
                "raw task_id was actually involved in the frozen full-F2 PIBT trace",
                row,
            )
    result: list[dict[str, Any]] = []
    for (slice_type, slice_id, definition), members in sorted(groups.items()):
        result.append(
            {
                "slice_type": slice_type,
                "slice_id": slice_id,
                "slice_definition": definition,
                **summarize_rows(members),
            }
        )
    return result


def _hard_gate_additions(
    payload: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> list[str]:
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        return ["RUNTIME_SUMMARY_MISSING"]
    timing = validation["timing"]
    blockers: list[str] = []
    exact_counts = {
        "selected_raw_bag_count": FULL_RAW_BAGS,
        "complete_raw_bag_count": FULL_RAW_BAGS,
        "selected_segment_count": FULL_SEGMENTS,
        "completed_segment_count": FULL_SEGMENTS,
    }
    for field, expected in exact_counts.items():
        if int(timing.get(field, -1)) != expected:
            blockers.append(
                f"{field.upper()}={timing.get(field)},expected={expected}"
            )
    summary_counts = {
        "requested_count": FULL_SEGMENTS,
        "completed_count": FULL_SEGMENTS,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "full_future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "two_step_reservation_count": 0,
        "priority_teacher_input_count": 0,
        "priority_future_route_input_count": 0,
        "priority_global_scan_count": 0,
        "scorer_teacher_input_count": 0,
        "scorer_future_route_input_count": 0,
        "scorer_future_schedule_input_count": 0,
        "scorer_runtime_global_scan_count": 0,
        "scorer_posthoc_input_count": 0,
        "first_edge_credit_global_scan_count": 0,
        "first_edge_credit_future_route_count": 0,
    }
    for field, expected in summary_counts.items():
        value = summary.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            blockers.append(f"MISSING_OR_NONINTEGER:{field}")
        elif value != expected:
            blockers.append(f"{field.upper()}={value},expected={expected}")
    if summary.get("event_limit_reached") is not False:
        blockers.append("EVENT_LIMIT_REACHED")
    if summary.get("time_limit_reached") is not False:
        blockers.append("TIME_LIMIT_REACHED")
    if int(summary.get("reservation_depth", -1)) != 1:
        blockers.append("RESERVATION_DEPTH_NOT_ONE")
    if summary.get("bag_future_path_field_present") is not False:
        blockers.append("BAG_FUTURE_PATH_FIELD_PRESENT")
    if summary.get("full_cie_astar_runtime_fallback") is not False:
        blockers.append("FULL_CIE_ASTAR_RUNTIME_FALLBACK")
    for field, blocker in (
        (
            "max_edges_selected_per_arrive",
            "MORE_THAN_ONE_EDGE_SELECTED_PER_ARRIVE",
        ),
        (
            "max_edges_selected_per_bag_per_decision",
            "MORE_THAN_ONE_EDGE_SELECTED_PER_BAG_DECISION",
        ),
    ):
        value = summary.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            blockers.append(f"MISSING_OR_NONINTEGER:{field}")
        elif value > 1:
            blockers.append(blocker)
    if int(summary.get("fault_event_count", -1)) != 0:
        blockers.append("NO_FAULT_FINALIST_HAS_FAULT_EVENTS")
    fault_events = payload.get("fault_events")
    if not isinstance(fault_events, list):
        blockers.append("FAULT_EVENT_TRACE_MISSING_OR_NONARRAY")
    elif fault_events:
        blockers.append(
            f"NO_FAULT_FINALIST_STORED_FAULT_EVENTS={len(fault_events)}"
        )
    if summary.get("fault_policy_enabled") is not True:
        blockers.append("FAULT_POLICY_ENABLE_ECHO_NOT_TRUE")
    if summary.get("first_edge_credit_physical_interlock_bypass") is not False:
        blockers.append("PHYSICAL_FAULT_INTERLOCK_BYPASS_NOT_FALSE")
    return blockers


def _runtime_request(
    finalist: Finalist,
    selection: cde.WorkloadSelection,
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    identity_sha256: str,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    controls = finalist.controls()
    capabilities = cde.inspect_runtime(executor)
    candidate = cde.Candidate(
        finalist.candidate_id,
        "priority",
        priority=finalist.priority_mode,
    )
    base = cde._runtime_base_kwargs(
        selection,
        binary=binary,
        search_path=search_path,
        root=root,
        candidate=candidate,
        config_sha256=identity_sha256,
    )
    base["scenario"] = f"g4irsf13_final_{finalist.candidate_id}"
    request, blockers = cde.bind_runtime_request(
        capabilities,
        base,
        controls,
        summary_only=True,
    )
    if blockers:
        raise JointEvaluationError(
            "runtime capability blockers: " + ";".join(blockers)
        )
    return request, controls


def _experiment_identity(
    finalist: Finalist,
    selection: cde.WorkloadSelection,
    *,
    binary: Path,
    selection_evidence: Mapping[str, Any],
    v3_dependency: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    binary_resolved = binary.resolve(strict=True)
    return {
        "schema": SCHEMA,
        "candidate": asdict(finalist),
        "controls": finalist.controls(),
        "repeat_protocol": {
            "repeat_count": REPEAT_COUNT,
            "deterministic_reproduction_not_independent_samples": True,
            "summary_only": True,
            "trace_limit": 0,
            "event_trace_limit": 0,
            "stop_after_first_h1_hard_failure": True,
        },
        "selection": {
            "selection_id": selection.selection_id,
            "segment_count": selection.segment_count,
            "raw_bag_count": selection.raw_bag_count,
            "selected_rows_sha256": selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                selection.selected_segment_ids_sha256
            ),
        },
        "protected_inputs": cde.assert_fixed_inputs(root),
        "repository_base_head": _repository_head(root),
        "binary": {
            "path": binary_resolved.as_posix(),
            "sha256": cde.file_sha256(binary_resolved),
        },
        "source_bundle": _source_bundle(root),
        "selection_evidence": dict(selection_evidence),
        "failed_projection_audit": selection_evidence[
            "failed_projection_audit"
        ],
        "v3_dependency": dict(v3_dependency),
        "reference_evidence": _file_bindings(
            REFERENCE_EVIDENCE_PATHS,
            root=root,
        ),
    }


def execute_repeat(
    finalist: Finalist,
    repeat_index: int,
    *,
    executor: Callable[..., Mapping[str, Any]],
    selection: cde.WorkloadSelection,
    binary: Path,
    search_path: Path,
    identity: Mapping[str, Any],
    contention_task_ids: set[int],
    contention_source_sha256: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    identity_sha256 = cde.canonical_sha256(identity)
    request, controls = _runtime_request(
        finalist,
        selection,
        executor=executor,
        binary=binary,
        search_path=search_path,
        identity_sha256=identity_sha256,
        root=root,
    )
    started = time.perf_counter()
    payload = executor(**request)
    wall_seconds = time.perf_counter() - started
    if not isinstance(payload, Mapping):
        raise JointEvaluationError("runtime returned a non-object payload")
    projection_hashes = algorithm_projection_hashes(payload)
    expected_binary = identity["binary"]
    validation = cde.validate_runtime_payload(
        payload,
        selection,
        controls,
        expected_binary=expected_binary,
    )
    hard_blockers = [
        *validation["control_echo_blockers"],
        *validation["provenance_blockers"],
        *validation["hard_blockers"],
        *_hard_gate_additions(payload, validation),
    ]
    runtime_bags = payload.get("bags")
    if not isinstance(runtime_bags, list):
        raise JointEvaluationError("runtime bags are missing")
    raw = g12.aggregate_raw_bag_timings(selection.rows, runtime_bags)
    enriched = augment_raw_bags(
        selection.rows,
        runtime_bags,
        raw,
        contention_task_ids=contention_task_ids,
    )
    metrics = summarize_rows(enriched)
    timing = validation["timing"]
    for field in (
        "original_entry_mean_minutes",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
    ):
        if not math.isclose(
            float(metrics[field]),
            float(timing[field]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            hard_blockers.append(f"INDEPENDENT_METRIC_MISMATCH:{field}")
    slices = build_slice_rows(enriched)
    slice_hash = cde.canonical_sha256(slices)
    summary = dict(validation["runtime_summary"])
    counters = dict(validation["counters"])
    counters["selected_segment_count"] = int(
        timing["selected_segment_count"]
    )
    counters["completed_segment_count"] = int(
        timing["completed_segment_count"]
    )
    selected_summary = {
        key: summary.get(key)
        for key in (
            "requested_count",
            "completed_count",
            "failed_count",
            "reservation_conflicts",
            "physical_fault_edge_entry_violation_count",
            "runtime_full_astar_calls",
            "global_reservation_scan_count",
            "full_future_routes_stored",
            "unresolved_deadlock_count",
            "two_step_reservation_count",
            "priority_teacher_input_count",
            "priority_future_route_input_count",
            "priority_global_scan_count",
            "scorer_teacher_input_count",
            "scorer_future_route_input_count",
            "scorer_future_schedule_input_count",
            "scorer_runtime_global_scan_count",
            "scorer_posthoc_input_count",
            "first_edge_credit_global_scan_count",
            "first_edge_credit_future_route_count",
            "event_limit_reached",
            "time_limit_reached",
            "reservation_depth",
            "bag_future_path_field_present",
            "full_cie_astar_runtime_fallback",
            "max_edges_selected_per_arrive",
            "max_edges_selected_per_bag_per_decision",
            "fault_event_count",
            "fault_policy_enabled",
            "first_edge_credit_physical_interlock_bypass",
            "priority_mode_echo",
            "framework_mode_echo",
            "resource_semantics_echo",
            "scorer_mode_echo",
            "pibt_mode_echo",
            "pibt_preference_mode_echo",
            "bounded_local_pibt_applicability_count",
            "bounded_local_pibt_attempt_count",
            "bounded_local_pibt_prepare_count",
            "bounded_local_pibt_validate_count",
            "bounded_local_pibt_commit_count",
            "bounded_local_pibt_rollback_count",
            "bounded_local_pibt_backtrack_count",
            "bounded_local_pibt_wait_for_cycle_count",
            "bounded_local_pibt_handoff_count",
            "bounded_local_pibt_max_inheritance_depth",
            "scorer_candidate_evaluation_count",
            "scorer_risk_abstain_count",
            "shield_rejection_count",
            "physical_fault_interlock_rejection_count",
            "decision_latency_us_p50",
            "decision_latency_us_p95",
            "decision_latency_us_p99",
            "runtime_seconds",
            "cpp_internal_accounted_bytes",
            "event_count",
        )
    }
    return {
        "schema": ARCHIVE_SCHEMA,
        "candidate_id": finalist.candidate_id,
        "candidate_role": finalist.role,
        "repeat_index": repeat_index,
        "execution_status": "EXECUTED",
        "gate_status": "PASS" if not hard_blockers else "FAIL",
        "hard_blockers": sorted(set(hard_blockers)),
        "experiment_identity_sha256": identity_sha256,
        "runtime_deterministic_sha256": projection_hashes[
            "runtime_algorithm_sha256"
        ],
        "legacy_runtime_projection_sha256": validation[
            "runtime_deterministic_sha256"
        ],
        "bags_sha256": projection_hashes["bags_sha256"],
        "junction_state_sha256": projection_hashes[
            "junction_state_sha256"
        ],
        "algorithm_summary_sha256": projection_hashes[
            "algorithm_summary_sha256"
        ],
        "trace_context_sha256": projection_hashes[
            "trace_context_sha256"
        ],
        "trace_lengths": projection_hashes["trace_lengths"],
        "nondeterministic_observations": {
            **projection_hashes["nondeterministic_observations"],
            "wall_seconds": wall_seconds,
        },
        "nonalgorithm_runtime_fields": projection_hashes[
            "excluded_field_names"
        ],
        "segment_result_sha256": validation["segment_result_sha256"],
        "slice_projection_sha256": slice_hash,
        "binary_sha256": expected_binary["sha256"],
        "source_bundle_sha256": identity["source_bundle"]["bundle_sha256"],
        "repository_base_head": identity["repository_base_head"],
        "map_raw_sha256": cde.CANONICAL_MAP_RAW_SHA256,
        "task_raw_sha256": cde.CANONICAL_SOURCE_RAW_SHA256,
        "input_selection_sha256": selection.selected_rows_sha256,
        "contention_source_sha256": contention_source_sha256,
        "wall_seconds": wall_seconds,
        "metrics": metrics,
        "counters": counters,
        "runtime_summary": selected_summary,
        "slices": slices,
    }


def _load_cached_repeats(
    cache_dir: Path,
    *,
    expected_identity_sha256: str,
    expected_count: int,
) -> list[dict[str, Any]] | None:
    pointer_path = cache_dir / "complete.json"
    if not pointer_path.is_file():
        return None
    pointer = _read_json(pointer_path)
    if pointer.get("experiment_identity_sha256") != expected_identity_sha256:
        raise JointEvaluationError("final repeat cache identity drift")
    bindings = pointer.get("repeat_bindings")
    if not isinstance(bindings, list) or len(bindings) != expected_count:
        raise JointEvaluationError("final repeat cache binding count drift")
    results: list[dict[str, Any]] = []
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise JointEvaluationError("repeat binding is not an object")
        relative = binding.get("path")
        if not isinstance(relative, str):
            raise JointEvaluationError("repeat binding path is missing")
        path = cache_dir / relative
        if cde.file_sha256(path) != binding.get("file_sha256"):
            raise JointEvaluationError("repeat archive file hash drift")
        value = _read_json(path)
        if (
            value.get("experiment_identity_sha256")
            != expected_identity_sha256
        ):
            raise JointEvaluationError("repeat result identity drift")
        value["archive_reused"] = True
        value["repeat_result_file_sha256"] = binding["file_sha256"]
        results.append(value)
    return results


def execute_finalist_repeats(
    finalist: Finalist,
    *,
    executor: Callable[..., Mapping[str, Any]],
    binary: Path,
    search_path: Path,
    selection_evidence: Mapping[str, Any],
    v3_dependency: Mapping[str, Any],
    contention_task_ids: set[int],
    contention_source_sha256: str,
    root: Path = ROOT,
    archive_root: Path | None = None,
) -> list[dict[str, Any]]:
    selection = cde.load_prefix_selection("full", root)
    identity = _experiment_identity(
        finalist,
        selection,
        binary=binary,
        selection_evidence=selection_evidence,
        v3_dependency=v3_dependency,
        root=root,
    )
    identity_sha256 = cde.canonical_sha256(identity)
    base = (
        archive_root
        if archive_root is not None
        else root / LOCAL_ARCHIVE
    )
    cache_dir = base / finalist.candidate_id / identity_sha256
    cached = _load_cached_repeats(
        cache_dir,
        expected_identity_sha256=identity_sha256,
        expected_count=REPEAT_COUNT,
    )
    if cached is not None:
        return cached
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / "active.lock"
    with cde.AttemptLock(
        lock_path,
        cache_key_value=identity_sha256,
        stale_seconds=3_600.0,
    ):
        cached = _load_cached_repeats(
            cache_dir,
            expected_identity_sha256=identity_sha256,
            expected_count=REPEAT_COUNT,
        )
        if cached is not None:
            return cached
        cde.atomic_write_json(cache_dir / "identity.json", identity)
        results: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []
        for repeat_index in range(1, REPEAT_COUNT + 1):
            result = execute_repeat(
                finalist,
                repeat_index,
                executor=executor,
                selection=selection,
                binary=binary,
                search_path=search_path,
                identity=identity,
                contention_task_ids=contention_task_ids,
                contention_source_sha256=contention_source_sha256,
                root=root,
            )
            relative = Path("repeats") / f"repeat_{repeat_index}.json"
            result_path = cache_dir / relative
            if result_path.exists():
                raise JointEvaluationError(
                    f"refusing to overwrite repeat evidence: {result_path}"
                )
            cde.atomic_write_json(result_path, result)
            digest = cde.file_sha256(result_path)
            result["repeat_result_file_sha256"] = digest
            result["archive_reused"] = False
            results.append(result)
            bindings.append(
                {
                    "repeat_index": repeat_index,
                    "path": relative.as_posix(),
                    "file_sha256": digest,
                    "gate_status": result["gate_status"],
                    "runtime_deterministic_sha256": result[
                        "runtime_deterministic_sha256"
                    ],
                    "bags_sha256": result["bags_sha256"],
                    "junction_state_sha256": result[
                        "junction_state_sha256"
                    ],
                    "algorithm_summary_sha256": result[
                        "algorithm_summary_sha256"
                    ],
                }
            )
            if result["gate_status"] != "PASS":
                # The first Q1 failure is a terminal negative result.  Other
                # candidates also fail closed rather than manufacturing five
                # successful-looking repeats after a hard failure.
                failure_pointer = {
                    "schema": ARCHIVE_SCHEMA,
                    "status": "STOPPED_ON_HARD_FAILURE",
                    "candidate_id": finalist.candidate_id,
                    "experiment_identity_sha256": identity_sha256,
                    "repeat_bindings": bindings,
                }
                cde.atomic_write_json(
                    cache_dir / "failed.json",
                    failure_pointer,
                )
                return results
        projection_hashes = {
            row["runtime_deterministic_sha256"] for row in results
        }
        segment_hashes = {row["segment_result_sha256"] for row in results}
        slice_hashes = {row["slice_projection_sha256"] for row in results}
        bag_hashes = {row["bags_sha256"] for row in results}
        junction_hashes = {
            row["junction_state_sha256"] for row in results
        }
        summary_hashes = {
            row["algorithm_summary_sha256"] for row in results
        }
        trace_context_hashes = {
            row["trace_context_sha256"] for row in results
        }
        if len(projection_hashes) != 1:
            raise JointEvaluationError("deterministic result hash drift")
        if (
            len(segment_hashes) != 1
            or len(slice_hashes) != 1
            or len(bag_hashes) != 1
            or len(junction_hashes) != 1
            or len(summary_hashes) != 1
            or len(trace_context_hashes) != 1
        ):
            raise JointEvaluationError(
                "bags/junction/summary/segment/slice repeat hash drift"
            )
        cde.atomic_write_json(
            cache_dir / "complete.json",
            {
                "schema": ARCHIVE_SCHEMA,
                "status": "COMPLETE",
                "candidate_id": finalist.candidate_id,
                "experiment_identity_sha256": identity_sha256,
                "repeat_count": REPEAT_COUNT,
                "runtime_deterministic_sha256": next(
                    iter(projection_hashes)
                ),
                "segment_result_sha256": next(iter(segment_hashes)),
                "slice_projection_sha256": next(iter(slice_hashes)),
                "bags_sha256": next(iter(bag_hashes)),
                "junction_state_sha256": next(iter(junction_hashes)),
                "algorithm_summary_sha256": next(iter(summary_hashes)),
                "trace_context_sha256": next(
                    iter(trace_context_hashes)
                ),
                "nonalgorithm_runtime_fields": sorted(
                    NONALGORITHM_RUNTIME_FIELDS
                ),
                "repeat_bindings": bindings,
            },
        )
        return results


def _repeat_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    metrics = row["metrics"]
    counters = row["counters"]
    summary = row["runtime_summary"]
    return {
        "schema": SCHEMA,
        "row_type": "FINAL_REPEAT",
        "candidate_id": row["candidate_id"],
        "candidate_role": row["candidate_role"],
        "repeat_index": row["repeat_index"],
        "execution_status": row["execution_status"],
        "gate_status": row["gate_status"],
        "blocker": ";".join(row["hard_blockers"]),
        **dict(metrics),
        "selected_segment_count": counters.get(
            "selected_segment_count", ""
        ),
        "completed_segment_count": counters.get("completed_segment_count", ""),
        "failed_segment_count": counters.get("failed_segment_count", ""),
        "conflict_count": counters.get("conflict_count", ""),
        "unsafe_entry_count": counters.get("unsafe_entry_count", ""),
        "runtime_full_astar_calls": counters.get(
            "runtime_full_astar_calls", ""
        ),
        "global_reservation_scan_count": counters.get(
            "global_reservation_scan_count", ""
        ),
        "future_routes_stored": counters.get("future_routes_stored", ""),
        "unresolved_deadlock_count": counters.get(
            "unresolved_deadlock_count", ""
        ),
        "event_limit_reached": counters.get("event_limit_reached", ""),
        "time_limit_reached": counters.get("time_limit_reached", ""),
        "reservation_depth": counters.get("reservation_depth", ""),
        "pibt_applicability_count": counters.get(
            "pibt_applicability_count", ""
        ),
        "pibt_attempt_count": counters.get("pibt_attempt_count", ""),
        "pibt_commit_count": counters.get("pibt_commit_count", ""),
        "pibt_rollback_count": counters.get("pibt_rollback_count", ""),
        "pibt_backtrack_count": counters.get("pibt_backtrack_count", ""),
        "pibt_handoff_count": counters.get("pibt_handoff_count", ""),
        "pibt_max_observed_depth": counters.get(
            "pibt_max_observed_depth", ""
        ),
        "model_confidence_status": "NOT_EXPOSED_FOR_FROZEN_S1",
        "shield_rejection_count": summary.get("shield_rejection_count", ""),
        "physical_interlock_rejection_count": summary.get(
            "physical_fault_interlock_rejection_count", ""
        ),
        "physical_fault_edge_entry_violation_count": summary.get(
            "physical_fault_edge_entry_violation_count", ""
        ),
        "fault_event_count": summary.get("fault_event_count", ""),
        "fault_policy_enabled": summary.get("fault_policy_enabled", ""),
        "physical_interlock_bypass": summary.get(
            "first_edge_credit_physical_interlock_bypass", ""
        ),
        "two_step_reservation_count": summary.get(
            "two_step_reservation_count", ""
        ),
        "max_edges_selected_per_arrive": summary.get(
            "max_edges_selected_per_arrive", ""
        ),
        "max_edges_selected_per_bag_per_decision": summary.get(
            "max_edges_selected_per_bag_per_decision", ""
        ),
        "priority_teacher_input_count": summary.get(
            "priority_teacher_input_count", ""
        ),
        "priority_future_route_input_count": summary.get(
            "priority_future_route_input_count", ""
        ),
        "priority_global_scan_count": summary.get(
            "priority_global_scan_count", ""
        ),
        "scorer_teacher_input_count": summary.get(
            "scorer_teacher_input_count", ""
        ),
        "scorer_future_route_input_count": summary.get(
            "scorer_future_route_input_count", ""
        ),
        "scorer_future_schedule_input_count": summary.get(
            "scorer_future_schedule_input_count", ""
        ),
        "scorer_runtime_global_scan_count": summary.get(
            "scorer_runtime_global_scan_count", ""
        ),
        "scorer_posthoc_input_count": summary.get(
            "scorer_posthoc_input_count", ""
        ),
        "priority_mode": summary.get("priority_mode_echo", ""),
        "runtime_deterministic_sha256": row[
            "runtime_deterministic_sha256"
        ],
        "legacy_runtime_projection_sha256": row[
            "legacy_runtime_projection_sha256"
        ],
        "bags_sha256": row["bags_sha256"],
        "junction_state_sha256": row["junction_state_sha256"],
        "algorithm_summary_sha256": row["algorithm_summary_sha256"],
        "trace_context_sha256": row["trace_context_sha256"],
        "segment_result_sha256": row["segment_result_sha256"],
        "slice_projection_sha256": row["slice_projection_sha256"],
        "repeat_result_file_sha256": row[
            "repeat_result_file_sha256"
        ],
        "binary_sha256": row["binary_sha256"],
        "source_bundle_sha256": row["source_bundle_sha256"],
        "repository_base_head": row["repository_base_head"],
        "map_raw_sha256": row["map_raw_sha256"],
        "task_raw_sha256": row["task_raw_sha256"],
        "input_selection_sha256": row["input_selection_sha256"],
        "archive_reused": row["archive_reused"],
        "wall_seconds": row["wall_seconds"],
    }


def _decision(
    h0: Mapping[str, Any],
    h1: Mapping[str, Any],
) -> dict[str, Any]:
    h0_mean = float(h0["metrics"]["original_entry_mean_minutes"])
    h1_mean = float(h1["metrics"]["original_entry_mean_minutes"])
    hard = h0["gate_status"] == "PASS" and h1["gate_status"] == "PASS"
    strict_v2 = h1_mean < FROZEN_V2_SAFE_RAW_ENTRY_MINUTES
    strict_f2 = h1_mean < h0_mean
    historical = h1_mean < HISTORICAL_HCA_RAW_ENTRY_MINUTES
    tail_pass = (
        float(h1["metrics"]["original_entry_p95_seconds"])
        <= float(h0["metrics"]["original_entry_p95_seconds"]) + 2.0
        and float(h1["metrics"]["original_entry_p99_seconds"])
        <= float(h0["metrics"]["original_entry_p99_seconds"]) + 4.0
    )
    if not hard or not tail_pass:
        status = "FAIL"
    elif strict_v2:
        status = "FRAMEWORK_PASS_LEARNING_FAIL"
    elif historical:
        status = "HISTORICAL_ONLY_PASS"
    else:
        status = "FAIL"
    return {
        "decision_status": status,
        "selected_candidate_id": "H1_Q1_THESIS_NO_LEARNING",
        "strict_win_vs_v2_safe": strict_v2,
        "strict_win_vs_f2": strict_f2,
        "strict_win_vs_historical_hca": historical,
        "all_1x_hard_gates_pass": hard,
        "tail_gate_pass": tail_pass,
        "delta_vs_v2_safe_seconds_per_bag": (
            h1_mean - FROZEN_V2_SAFE_RAW_ENTRY_MINUTES
        )
        * 60.0,
        "delta_vs_f2_seconds_per_bag": (h1_mean - h0_mean) * 60.0,
        "delta_vs_historical_hca_seconds_per_bag": (
            h1_mean - HISTORICAL_HCA_RAW_ENTRY_MINUTES
        )
        * 60.0,
        "strong_pass_margin_seconds_per_bag": (
            FROZEN_V2_SAFE_RAW_ENTRY_MINUTES - h1_mean
        )
        * 60.0,
        "v3_contribution_proven": False,
        "deployment_recommendation": (
            "KEEP_F2_FROZEN_CONTROL_NO_NEW_CANDIDATE_PROMOTION"
        ),
    }


def _reference_rows(
    h0: Mapping[str, Any],
    h1: Mapping[str, Any],
    *,
    root: Path,
) -> list[dict[str, Any]]:
    old_full_path = root / "outputs/tables/g4irsf12_original_scale_full_ab.csv"
    old_rows = _read_csv(old_full_path)
    p0 = [
        row
        for row in old_rows
        if row.get("candidate_id") == "J_CTRL_PIBT_OFF"
    ]
    if len(p0) != REPEAT_COUNT:
        raise JointEvaluationError("sealed PIBT-off control repeat count drift")
    p0_counts = {
        (
            row.get("complete_raw_bag_count"),
            row.get("completed_segment_count"),
            row.get("unresolved_deadlock_count"),
            row.get("event_limit_reached"),
        )
        for row in p0
    }
    if len(p0_counts) != 1:
        raise JointEvaluationError("sealed PIBT-off control is inconsistent")
    fault_path = root / "outputs/tables/g4irsf13_fault_causal_ab.csv"
    fault_rows = _read_csv(fault_path)
    shield = [
        row
        for row in fault_rows
        if row.get("case_id") == "G1_physical_shield_only"
    ]
    if len(shield) != 1:
        raise JointEvaluationError("fault-policy ablation reference is missing")

    def reference(
        candidate_id: str,
        role: str,
        mean: float | str,
        status: str,
        evidence_path: Path | None,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "row_type": "REFERENCE_CONTROL",
            "candidate_id": candidate_id,
            "control_role": role,
            "execution_status": status,
            "gate_status": extra.pop("gate_status", "REFERENCE"),
            "original_entry_mean_minutes": mean,
            "evidence_path": evidence_path.as_posix() if evidence_path else "",
            "evidence_file_sha256": (
                cde.file_sha256(root / evidence_path)
                if evidence_path
                else ""
            ),
            **extra,
        }

    h0_mean = h0["metrics"]["original_entry_mean_minutes"]
    h1_mean = h1["metrics"]["original_entry_mean_minutes"]
    return [
        reference(
            "HISTORICAL_PARSED_HCA",
            "historical parsed HCA raw-entry control",
            HISTORICAL_HCA_RAW_ENTRY_MINUTES,
            "RECONCILED_REFERENCE",
            Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
        ),
        reference(
            "CORRECTED_MATCHED_HCA_TARGET",
            "corrected matched HCA raw-entry target",
            HISTORICAL_HCA_RAW_ENTRY_MINUTES,
            "RECONCILED_REFERENCE",
            Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
        ),
        reference(
            "FROZEN_V2_SAFE",
            "frozen v2-safe raw-entry control",
            FROZEN_V2_SAFE_RAW_ENTRY_MINUTES,
            "RECONCILED_REFERENCE",
            Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
        ),
        reference(
            "F1_RULE_BASELINE",
            "F1 bounded-PIBT rule reference",
            F1_RAW_ENTRY_MINUTES,
            "SEALED_REFERENCE",
            Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
        ),
        reference(
            "F2_FROZEN_RECONCILED",
            "F2 frozen reconciled reference; fresh H0 is authoritative",
            F2_RECONCILED_RAW_ENTRY_MINUTES,
            "SEALED_REFERENCE",
            Path("artifacts/policies/g4irsf12_denominator_reconciliation.json"),
            fresh_h0_original_entry_mean_minutes=h0_mean,
        ),
        reference(
            "PIBT_OFF_CENSORED",
            "no-PIBT ablation; completion/deadlock only",
            "",
            "PARTIAL_CENSORED",
            Path("outputs/tables/g4irsf12_original_scale_full_ab.csv"),
            gate_status="FAIL",
            complete_raw_bag_count=p0[0]["complete_raw_bag_count"],
            completed_segment_count=p0[0]["completed_segment_count"],
            unresolved_deadlock_count=p0[0]["unresolved_deadlock_count"],
            event_limit_reached=p0[0]["event_limit_reached"],
            blocker="PRIMARY_TTH_CENSORED_NOT_COMPARABLE",
        ),
        reference(
            "NO_PIBT_ABLATION",
            "explicit no-PIBT ablation alias of the sealed censored control",
            "",
            "PARTIAL_CENSORED_ALIAS",
            Path("outputs/tables/g4irsf12_original_scale_full_ab.csv"),
            gate_status="FAIL",
            alias_of="PIBT_OFF_CENSORED",
            complete_raw_bag_count=p0[0]["complete_raw_bag_count"],
            completed_segment_count=p0[0]["completed_segment_count"],
            unresolved_deadlock_count=p0[0]["unresolved_deadlock_count"],
            event_limit_reached=p0[0]["event_limit_reached"],
            blocker="PRIMARY_TTH_CENSORED_NOT_COMPARABLE",
        ),
        reference(
            "BEST_NEW_CANDIDATE",
            "best new finalist alias",
            h1_mean,
            "EXECUTED_ALIAS",
            None,
            alias_of="H1_Q1_THESIS_NO_LEARNING",
            runtime_deterministic_sha256=h1[
                "runtime_deterministic_sha256"
            ],
        ),
        reference(
            "NO_LEARNING_ABLATION",
            "no-new-learning ablation is the H1 finalist itself",
            h1_mean,
            "EXECUTED_ALIAS",
            None,
            alias_of="H1_Q1_THESIS_NO_LEARNING",
            runtime_deterministic_sha256=h1[
                "runtime_deterministic_sha256"
            ],
        ),
        reference(
            "FAULT_POLICY_ABLATION",
            "real-map informative physical-shield-only Stage-G control",
            "",
            "SMALL_REAL_TASK_REFERENCE",
            Path("outputs/tables/g4irsf13_fault_causal_ab.csv"),
            gate_status=shield[0]["gate_status"],
            blocker=(
                "NO_ADDITIONAL_FULL_RUN; H3 blocked by v3 offline gate"
            ),
        ),
    ]


def build_table_rows(
    results: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    root: Path = ROOT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if set(results) != {item.candidate_id for item in FINALISTS}:
        raise JointEvaluationError("fresh finalist result set drift")
    for finalist in FINALISTS:
        rows = list(results[finalist.candidate_id])
        if len(rows) != REPEAT_COUNT:
            raise JointEvaluationError(
                f"{finalist.candidate_id} lacks five deterministic repeats"
            )
        if any(row["gate_status"] != "PASS" for row in rows):
            raise JointEvaluationError(
                f"{finalist.candidate_id} has a hard-gate failure"
            )
        for field in (
            "runtime_deterministic_sha256",
            "bags_sha256",
            "junction_state_sha256",
            "algorithm_summary_sha256",
            "trace_context_sha256",
            "segment_result_sha256",
            "slice_projection_sha256",
            "binary_sha256",
            "source_bundle_sha256",
            "repository_base_head",
            "map_raw_sha256",
            "task_raw_sha256",
            "input_selection_sha256",
        ):
            if len({row[field] for row in rows}) != 1:
                raise JointEvaluationError(
                    f"{finalist.candidate_id} repeat drift: {field}"
                )
    h0 = results["H0_F2_FROZEN"][0]
    h1 = results["H1_Q1_THESIS_NO_LEARNING"][0]
    decision = _decision(h0, h1)
    table: list[dict[str, Any]] = []
    for finalist in FINALISTS:
        candidate_rows = results[finalist.candidate_id]
        table.extend(_repeat_projection(row) for row in candidate_rows)
        first = candidate_rows[0]
        metrics = dict(first["metrics"])
        table.append(
            {
                "schema": SCHEMA,
                "row_type": "FINAL_SUMMARY",
                "candidate_id": finalist.candidate_id,
                "candidate_role": finalist.role,
                "execution_status": "EXECUTED",
                "gate_status": "PASS",
                "deterministic_repeat_count": REPEAT_COUNT,
                "independent_statistical_sample_count": 1,
                **metrics,
                "delta_vs_v2_safe_seconds_per_bag": (
                    float(metrics["original_entry_mean_minutes"])
                    - FROZEN_V2_SAFE_RAW_ENTRY_MINUTES
                )
                * 60.0,
                "delta_vs_f2_seconds_per_bag": (
                    float(metrics["original_entry_mean_minutes"])
                    - float(h0["metrics"]["original_entry_mean_minutes"])
                )
                * 60.0,
                "strict_win_vs_v2_safe": (
                    float(metrics["original_entry_mean_minutes"])
                    < FROZEN_V2_SAFE_RAW_ENTRY_MINUTES
                ),
                "strict_win_vs_f2": (
                    float(metrics["original_entry_mean_minutes"])
                    < float(h0["metrics"]["original_entry_mean_minutes"])
                ),
                "runtime_deterministic_sha256": first[
                    "runtime_deterministic_sha256"
                ],
                "bags_sha256": first["bags_sha256"],
                "junction_state_sha256": first[
                    "junction_state_sha256"
                ],
                "algorithm_summary_sha256": first[
                    "algorithm_summary_sha256"
                ],
                "trace_context_sha256": first[
                    "trace_context_sha256"
                ],
                "segment_result_sha256": first["segment_result_sha256"],
                "slice_projection_sha256": first[
                    "slice_projection_sha256"
                ],
                "binary_sha256": first["binary_sha256"],
                "source_bundle_sha256": first["source_bundle_sha256"],
                "repository_base_head": first["repository_base_head"],
                "map_raw_sha256": first["map_raw_sha256"],
                "task_raw_sha256": first["task_raw_sha256"],
                "input_selection_sha256": first[
                    "input_selection_sha256"
                ],
            }
        )
    h0_slices = {
        (row["slice_type"], row["slice_id"]): row
        for row in h0["slices"]
    }
    for finalist in FINALISTS:
        first = results[finalist.candidate_id][0]
        for slice_row in first["slices"]:
            key = (slice_row["slice_type"], slice_row["slice_id"])
            baseline = h0_slices.get(key)
            if baseline is None:
                raise JointEvaluationError(
                    f"slice denominator mismatch: {key}"
                )
            table.append(
                {
                    "schema": SCHEMA,
                    "row_type": "SLICE",
                    "candidate_id": finalist.candidate_id,
                    "candidate_role": finalist.role,
                    "execution_status": "EXECUTED",
                    "gate_status": (
                        "PASS"
                        if slice_row["comparison_eligible"]
                        else "FAIL"
                    ),
                    **dict(slice_row),
                    "delta_vs_h0_seconds_per_bag": (
                        float(slice_row["original_entry_mean_minutes"])
                        - float(baseline["original_entry_mean_minutes"])
                    )
                    * 60.0,
                    "runtime_deterministic_sha256": first[
                        "runtime_deterministic_sha256"
                    ],
                    "slice_projection_sha256": first[
                        "slice_projection_sha256"
                    ],
                }
            )
    table.extend(_reference_rows(h0, h1, root=root))
    for candidate_id, role in (
        ("H2_V3_RESIDUAL", "best v3 residual"),
        (
            "H3_V3_RESIDUAL_FAULT_CONTROL_NO_FAULT",
            "best v3 residual plus fault control in no-fault mode",
        ),
    ):
        table.append(
            {
                "schema": SCHEMA,
                "row_type": "FINALIST_NOT_RUN",
                "candidate_id": candidate_id,
                "candidate_role": role,
                "execution_status": "NOT_RUN",
                "gate_status": "NOT_EVALUATED",
                "blocker": V3_BLOCKER,
            }
        )
    return table, decision


def _csv_columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    preferred = [
        "schema",
        "row_type",
        "candidate_id",
        "candidate_role",
        "control_role",
        "repeat_index",
        "slice_type",
        "slice_id",
        "slice_definition",
        "execution_status",
        "gate_status",
        "blocker",
        "selected_raw_bag_count",
        "complete_raw_bag_count",
        "selected_segment_count",
        "completed_segment_count",
        "failed_segment_count",
        "completion_rate",
        "original_entry_mean_minutes",
        "original_entry_median_seconds",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "original_entry_max_seconds",
        "scheduled_dwell_mean_minutes",
        "source_wait_mean_minutes",
        "network_time_mean_minutes",
        "decision_sensitive_mean_minutes",
        "path_edge_count_mean",
        "edge_travel_time_mean_seconds",
        "loop_detour_time_mean_seconds",
        "loop_count",
        "deadline_miss_raw_bag_count",
        "delta_vs_v2_safe_seconds_per_bag",
        "delta_vs_f2_seconds_per_bag",
        "delta_vs_h0_seconds_per_bag",
        "strict_win_vs_v2_safe",
        "strict_win_vs_f2",
        "conflict_count",
        "unsafe_entry_count",
        "runtime_full_astar_calls",
        "global_reservation_scan_count",
        "future_routes_stored",
        "unresolved_deadlock_count",
        "event_limit_reached",
        "time_limit_reached",
        "reservation_depth",
        "pibt_applicability_count",
        "pibt_attempt_count",
        "pibt_commit_count",
        "pibt_rollback_count",
        "pibt_backtrack_count",
        "pibt_handoff_count",
        "pibt_max_observed_depth",
        "model_confidence_status",
        "shield_rejection_count",
        "physical_interlock_rejection_count",
        "physical_fault_edge_entry_violation_count",
        "fault_event_count",
        "fault_policy_enabled",
        "physical_interlock_bypass",
        "two_step_reservation_count",
        "max_edges_selected_per_arrive",
        "max_edges_selected_per_bag_per_decision",
        "priority_teacher_input_count",
        "priority_future_route_input_count",
        "priority_global_scan_count",
        "scorer_teacher_input_count",
        "scorer_future_route_input_count",
        "scorer_future_schedule_input_count",
        "scorer_runtime_global_scan_count",
        "scorer_posthoc_input_count",
        "priority_mode",
        "deterministic_repeat_count",
        "independent_statistical_sample_count",
        "runtime_deterministic_sha256",
        "legacy_runtime_projection_sha256",
        "bags_sha256",
        "junction_state_sha256",
        "algorithm_summary_sha256",
        "trace_context_sha256",
        "segment_result_sha256",
        "slice_projection_sha256",
        "repeat_result_file_sha256",
        "binary_sha256",
        "source_bundle_sha256",
        "repository_base_head",
        "map_raw_sha256",
        "task_raw_sha256",
        "input_selection_sha256",
        "archive_reused",
        "wall_seconds",
        "evidence_path",
        "evidence_file_sha256",
        "alias_of",
        "fresh_h0_original_entry_mean_minutes",
    ]
    seen = set(preferred)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                preferred.append(key)
    return preferred


def _report(
    results: Mapping[str, Sequence[Mapping[str, Any]]],
    table_rows: Sequence[Mapping[str, Any]],
    decision: Mapping[str, Any],
    selection_evidence: Mapping[str, Any],
    v3_dependency: Mapping[str, Any],
) -> bytes:
    h0 = results["H0_F2_FROZEN"][0]
    h1 = results["H1_Q1_THESIS_NO_LEARNING"][0]
    h0m = h0["metrics"]
    h1m = h1["metrics"]
    repeat_lines = []
    for candidate_id in ("H0_F2_FROZEN", "H1_Q1_THESIS_NO_LEARNING"):
        rows = results[candidate_id]
        repeat_lines.append(
            f"| {candidate_id} | {len(rows)} | "
            f"`{rows[0]['runtime_deterministic_sha256']}` | "
            f"`{rows[0]['binary_sha256']}` | PASS |"
        )
    slice_rows = [
        row
        for row in table_rows
        if row.get("row_type") == "SLICE"
        and row.get("candidate_id") == "H1_Q1_THESIS_NO_LEARNING"
    ]
    highlighted = [
        row
        for row in slice_rows
        if row.get("slice_type")
        in {"busy_hour", "ebs_release", "contention", "storage_lifecycle"}
    ]
    slice_lines = [
        "| {slice_type} | {slice_id} | {selected_raw_bag_count} | "
        "{original_entry_mean_minutes:.12f} | "
        "{delta_vs_h0_seconds_per_bag:+.9f} |".format(
            **{
                **row,
                "original_entry_mean_minutes": float(
                    row["original_entry_mean_minutes"]
                ),
                "delta_vs_h0_seconds_per_bag": float(
                    row["delta_vs_h0_seconds_per_bag"]
                ),
            }
        )
        for row in highlighted
    ]
    lines = [
        "# G4IRSF13 Original-Scale Joint Decision",
        "",
        f"Status: `{decision['decision_status']}`.",
        "",
        "H0 and H1 both completed the protected original 1x population. H1 "
        "was selected before the full run by the interpretable Q1 thesis-local "
        "tie-break; no empirical superiority was inferred from candidate IDs. "
        "Q0, Q3, P1, and P3 remain explicitly recorded as equal 8192 controls.",
        "",
        "## Primary raw-entry result",
        "",
        "| Candidate/control | Mean (min) | Median (s) | p95 (s) | p99 (s) | Max (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| H0 F2 frozen | {float(h0m['original_entry_mean_minutes']):.12f} | "
            f"{float(h0m['original_entry_median_seconds']):.6f} | "
            f"{float(h0m['original_entry_p95_seconds']):.6f} | "
            f"{float(h0m['original_entry_p99_seconds']):.6f} | "
            f"{float(h0m['original_entry_max_seconds']):.6f} |"
        ),
        (
            f"| H1 Q1 no-learning | {float(h1m['original_entry_mean_minutes']):.12f} | "
            f"{float(h1m['original_entry_median_seconds']):.6f} | "
            f"{float(h1m['original_entry_p95_seconds']):.6f} | "
            f"{float(h1m['original_entry_p99_seconds']):.6f} | "
            f"{float(h1m['original_entry_max_seconds']):.6f} |"
        ),
        (
            f"| frozen v2-safe raw-entry | {FROZEN_V2_SAFE_RAW_ENTRY_MINUTES:.12f} "
            "| N/A | N/A | N/A | N/A |"
        ),
        (
            f"| corrected historical HCA raw-entry | "
            f"{HISTORICAL_HCA_RAW_ENTRY_MINUTES:.12f} | N/A | N/A | N/A | N/A |"
        ),
        "",
        f"H1 delta versus v2-safe: "
        f"`{float(decision['delta_vs_v2_safe_seconds_per_bag']):+.9f} s/bag`; "
        f"delta versus fresh H0/F2: "
        f"`{float(decision['delta_vs_f2_seconds_per_bag']):+.9f} s/bag`.",
        "",
        "The primary gate uses the Stage-B reconciled raw-entry v2 value "
        "`41.49530698780892 min`. The old `4.124305453` number is "
        "pass-time anchored and is not used as a raw-entry comparator.",
        "",
        "## Timing decomposition",
        "",
        "| Candidate | Scheduled dwell (min) | Source wait (min) | Network (min) | Decision-sensitive (min) | Mean path edges | Loop detour (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| H0 | {float(h0m['scheduled_dwell_mean_minutes']):.12f} | "
            f"{float(h0m['source_wait_mean_minutes']):.12f} | "
            f"{float(h0m['network_time_mean_minutes']):.12f} | "
            f"{float(h0m['decision_sensitive_mean_minutes']):.12f} | "
            f"{float(h0m['path_edge_count_mean']):.6f} | "
            f"{float(h0m['loop_detour_time_mean_seconds']):.6f} |"
        ),
        (
            f"| H1 | {float(h1m['scheduled_dwell_mean_minutes']):.12f} | "
            f"{float(h1m['source_wait_mean_minutes']):.12f} | "
            f"{float(h1m['network_time_mean_minutes']):.12f} | "
            f"{float(h1m['decision_sensitive_mean_minutes']):.12f} | "
            f"{float(h1m['path_edge_count_mean']):.6f} | "
            f"{float(h1m['loop_detour_time_mean_seconds']):.6f} |"
        ),
        "",
        "## Five deterministic repeats",
        "",
        "| Candidate | Repeats | Result hash | Binary hash | Hard gates |",
        "| --- | ---: | --- | --- | --- |",
        *repeat_lines,
        "",
        "The five identical repeats are deterministic reproductions, not five "
        "independent statistical samples. The independent statistical sample "
        "count is therefore recorded as one per candidate.",
        "",
        "An earlier five-run H1 attempt is retained as "
        "`FAILED_PROJECTION_AUDIT`: its legacy hash admitted a host-throughput "
        "measurement and did not retain complete bags/junction/full-summary "
        "component hashes. Those runs all passed runtime hard gates but are "
        "not reused as final equivalence evidence. The replacement protocol "
        "hashes complete bags, junction state, and the full algorithm summary "
        "while excluding only an explicit timing/RSS whitelist.",
        "",
        "A subsequent ten-run replacement passed every runtime hard gate but "
        "is retained as `PROJECTION_VALIDATOR_FAILURE`: its committed CSV "
        "looked for the completed-segment count in the counter projection "
        "instead of the independently validated timing projection. Those "
        "runs are not reused; this final identity binds requested/completed "
        "segment counts directly from the timing projection.",
        "",
        "A later ten-run replacement is retained as "
        "`REPORT_ENCODING_VALIDATOR_FAILURE`: non-ASCII dash characters in "
        "the formal report were not portable across legacy decoders. Those "
        "runs are not reused; final report text is strict ASCII.",
        "",
        "## Hard gates",
        "",
        "Both candidates recorded 28,506/28,506 complete raw bags and "
        "43,603/43,603 completed segments; zero failed segments, conflicts, "
        "unsafe entries, runtime A*/CIE calls, global reservation scans, "
        "stored future routes, and unresolved deadlocks; no event/time limit; "
        "and reservation depth 1. Map, input, binary, source, segment-result, "
        "slice, and deterministic runtime hashes are repeat-bound.",
        "",
        "## Real-input robustness slices",
        "",
        "The CSV includes every protected source, goal, clock hour, contiguous "
        "six-hour input block, direct/EBS storage lifecycle, the actual frozen "
        "F2 PIBT-involved task set, and the empirically busiest input hour. "
        "Highlighted H1 rows:",
        "",
        "| Slice | ID | Bags | Raw-entry mean (min) | Delta vs H0 (s/bag) |",
        "| --- | --- | ---: | ---: | ---: |",
        *slice_lines,
        "",
        "## PIBT and learning conclusion",
        "",
        "The history-closed matched contention gate passed, but P1-P4 were "
        "outcome-identical and P0 was 0.069048448 s/bag faster on that 8192 "
        "diagnostic. Dodge changed four unique-exit penalties without changing "
        "outcomes; regret had zero prior hits and is NOT_APPLICABLE. These are "
        "negative mechanism findings, not hidden promotion evidence.",
        "",
        f"H2 and H3 are `NOT_RUN`: `{v3_dependency['blocker']}`. The v3 "
        "offline gate failed, runtime eligibility is false, and closed-loop "
        "execution is not authorized. Consequently independent learning "
        "contribution is not proven.",
        "",
        "## Decision",
        "",
        f"- selected evaluated candidate: `{decision['selected_candidate_id']}`",
        f"- strict win vs v2-safe: `{decision['strict_win_vs_v2_safe']}`",
        f"- strict win vs F2: `{decision['strict_win_vs_f2']}`",
        f"- all original-1x hard gates pass: `{decision['all_1x_hard_gates_pass']}`",
        f"- final label: `{decision['decision_status']}`",
        "",
        "H1 beats the corrected historical HCA control but does not beat "
        "frozen v2-safe and does not independently beat F2. The scientifically "
        "valid outcome is therefore historical-only pass, with F2 retained and "
        "no new candidate promoted.",
        "",
        "Selection evidence status: "
        f"`{selection_evidence['status']}`. No full candidate beyond H0/H1 "
        "was launched.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build_bundle(
    results: Mapping[str, Sequence[Mapping[str, Any]]],
    decision: Mapping[str, Any],
    *,
    table_sha256: str,
    report_sha256: str,
    selection_evidence: Mapping[str, Any],
    v3_dependency: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    repeat_bindings: list[dict[str, Any]] = []
    for finalist in FINALISTS:
        rows = results[finalist.candidate_id]
        repeat_bindings.append(
            {
                "candidate_id": finalist.candidate_id,
                "role": finalist.role,
                "priority_mode": finalist.priority_mode,
                "repeat_count": len(rows),
                "runtime_deterministic_sha256": rows[0][
                    "runtime_deterministic_sha256"
                ],
                "bags_sha256": rows[0]["bags_sha256"],
                "junction_state_sha256": rows[0][
                    "junction_state_sha256"
                ],
                "algorithm_summary_sha256": rows[0][
                    "algorithm_summary_sha256"
                ],
                "trace_context_sha256": rows[0][
                    "trace_context_sha256"
                ],
                "segment_result_sha256": rows[0]["segment_result_sha256"],
                "slice_projection_sha256": rows[0][
                    "slice_projection_sha256"
                ],
                "binary_sha256": rows[0]["binary_sha256"],
                "source_bundle_sha256": rows[0]["source_bundle_sha256"],
                "repository_base_head": rows[0][
                    "repository_base_head"
                ],
                "map_raw_sha256": rows[0]["map_raw_sha256"],
                "task_raw_sha256": rows[0]["task_raw_sha256"],
                "input_selection_sha256": rows[0][
                    "input_selection_sha256"
                ],
                "repeat_result_file_sha256": [
                    row["repeat_result_file_sha256"] for row in rows
                ],
                "hard_gate_statuses": [row["gate_status"] for row in rows],
                "metrics": rows[0]["metrics"],
            }
        )
    bundle = {
        "schema": BUNDLE_SCHEMA,
        # Top-level machine-readable J-stage fields requested by protocol.
        "strict_win_vs_v2_safe": bool(
            decision["strict_win_vs_v2_safe"]
        ),
        "strict_win_vs_f2": bool(decision["strict_win_vs_f2"]),
        "all_1x_hard_gates_pass": bool(
            decision["all_1x_hard_gates_pass"]
        ),
        "selected_candidate_id": str(decision["selected_candidate_id"]),
        "decision_status": str(decision["decision_status"]),
        "status": "COMPLETE",
        "experiment_base_head": results[FINALISTS[0].candidate_id][0][
            "repository_base_head"
        ],
        "v3_contribution_proven": False,
        "h2_execution_status": "NOT_RUN",
        "h2_not_run_reason": V3_BLOCKER,
        "h3_execution_status": "NOT_RUN",
        "h3_not_run_reason": V3_BLOCKER,
        "failed_projection_audit": dict(
            selection_evidence["failed_projection_audit"]
        ),
        "projection_validator_failure_audit": dict(
            selection_evidence["projection_validator_failure_audit"]
        ),
        "report_encoding_validator_failure_audit": dict(
            selection_evidence[
                "report_encoding_validator_failure_audit"
            ]
        ),
        "deployment_recommendation": decision[
            "deployment_recommendation"
        ],
        "full_candidate_count": 2,
        "maximum_full_candidates": MAX_FULL_FINALISTS,
        "deterministic_repeat_semantics": (
            "five reproducibility checks per candidate; not independent samples"
        ),
        "algorithm_equivalence_protocol": {
            "complete_bags_hash_required": True,
            "junction_state_hash_required": True,
            "full_algorithm_summary_hash_required": True,
            "trace_context_hash_required": True,
            "excluded_nonalgorithm_fields": sorted(
                NONALGORITHM_RUNTIME_FIELDS
            ),
        },
        "primary_denominator": "original_entry_time_tth",
        "corrected_controls": {
            "historical_hca_raw_entry_minutes": (
                HISTORICAL_HCA_RAW_ENTRY_MINUTES
            ),
            "frozen_v2_safe_raw_entry_minutes": (
                FROZEN_V2_SAFE_RAW_ENTRY_MINUTES
            ),
            "f1_raw_entry_minutes": F1_RAW_ENTRY_MINUTES,
            "f2_reconciled_raw_entry_minutes": (
                F2_RECONCILED_RAW_ENTRY_MINUTES
            ),
            "scheduled_dwell_minutes": SCHEDULED_DWELL_MINUTES,
            "old_pass_anchored_v2_is_primary": False,
        },
        "decision": dict(decision),
        "selection_evidence": dict(selection_evidence),
        "v3_dependency": dict(v3_dependency),
        "not_run_finalists": [
            {
                "candidate_id": "H2_V3_RESIDUAL",
                "execution_status": "NOT_RUN",
                "reason": V3_BLOCKER,
            },
            {
                "candidate_id": (
                    "H3_V3_RESIDUAL_FAULT_CONTROL_NO_FAULT"
                ),
                "execution_status": "NOT_RUN",
                "reason": V3_BLOCKER,
            },
        ],
        "repeat_bindings": repeat_bindings,
        "source_bundle": _source_bundle(root),
        "protected_inputs": cde.assert_fixed_inputs(root),
        "output_bindings": {
            TABLE_PATH.as_posix(): table_sha256,
            REPORT_PATH.as_posix(): report_sha256,
        },
        "reference_evidence": _file_bindings(
            REFERENCE_EVIDENCE_PATHS,
            root=root,
        ),
        "slice_protocol": {
            "continuous_block_seconds": CONTINUOUS_BLOCK_SECONDS,
            "source": "protected original_start",
            "goal": "protected original_goal",
            "busy_hour": (
                "highest protected raw-bag count clock hour; tie lowest"
            ),
            "ebs_release": "protected storage_out lifecycle",
            "contention": (
                "actual frozen full-F2 PIBT-involved task IDs"
            ),
        },
    }
    bundle["bundle_sha256"] = cde.canonical_sha256(bundle)
    return bundle


def write_outputs(
    results: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    selection_evidence: Mapping[str, Any],
    v3_dependency: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    table_rows, decision = build_table_rows(results, root=root)
    table_path = root / TABLE_PATH
    report_path = root / REPORT_PATH
    bundle_path = root / BUNDLE_PATH
    cde.atomic_write_csv(
        table_path,
        _csv_columns(table_rows),
        table_rows,
    )
    report = _report(
        results,
        table_rows,
        decision,
        selection_evidence,
        v3_dependency,
    )
    cde._atomic_write(report_path, report)
    bundle = build_bundle(
        results,
        decision,
        table_sha256=cde.file_sha256(table_path),
        report_sha256=cde.file_sha256(report_path),
        selection_evidence=selection_evidence,
        v3_dependency=v3_dependency,
        root=root,
    )
    cde.atomic_write_json(bundle_path, bundle)
    return {
        "decision": decision,
        "table_row_count": len(table_rows),
        "table_sha256": cde.file_sha256(table_path),
        "report_sha256": cde.file_sha256(report_path),
        "bundle_sha256": cde.file_sha256(bundle_path),
    }


def validate_committed_outputs(root: Path = ROOT) -> dict[str, Any]:
    table_path = root / TABLE_PATH
    report_path = root / REPORT_PATH
    bundle_path = root / BUNDLE_PATH
    rows = _read_csv(table_path)
    bundle = _read_json(bundle_path)
    report = report_path.read_text(encoding="utf-8")
    try:
        report.encode("ascii")
    except UnicodeEncodeError as exc:
        raise JointEvaluationError(
            "committed report is not strict ASCII"
        ) from exc
    for forbidden in ("\u0431\u043a", "P1\u0438CP4"):
        if forbidden in report:
            raise JointEvaluationError(
                f"committed report contains mojibake: {forbidden!r}"
            )
    repeats = [row for row in rows if row.get("row_type") == "FINAL_REPEAT"]
    if len(repeats) != 2 * REPEAT_COUNT:
        raise JointEvaluationError("committed final repeat count is not 10")
    for candidate_id in (
        "H0_F2_FROZEN",
        "H1_Q1_THESIS_NO_LEARNING",
    ):
        candidate_rows = [
            row for row in repeats if row.get("candidate_id") == candidate_id
        ]
        if len(candidate_rows) != REPEAT_COUNT:
            raise JointEvaluationError(
                f"{candidate_id} committed repeat count drift"
            )
        if any(
            row.get("execution_status") != "EXECUTED"
            or row.get("gate_status") != "PASS"
            or row.get("blocker") != ""
            for row in candidate_rows
        ):
            raise JointEvaluationError(f"{candidate_id} hard gate drift")
        for field in (
            "runtime_deterministic_sha256",
            "bags_sha256",
            "junction_state_sha256",
            "algorithm_summary_sha256",
            "trace_context_sha256",
            "segment_result_sha256",
            "slice_projection_sha256",
            "binary_sha256",
            "source_bundle_sha256",
            "repository_base_head",
            "map_raw_sha256",
            "task_raw_sha256",
            "input_selection_sha256",
            "original_entry_mean_minutes",
            "original_entry_p95_seconds",
            "original_entry_p99_seconds",
        ):
            values = {row.get(field, "") for row in candidate_rows}
            if len(values) != 1 or "" in values:
                raise JointEvaluationError(
                    f"{candidate_id} deterministic field drift: {field}"
                )
        exact_hard_gate_fields = {
            "selected_raw_bag_count": str(FULL_RAW_BAGS),
            "complete_raw_bag_count": str(FULL_RAW_BAGS),
            "selected_segment_count": str(FULL_SEGMENTS),
            "completed_segment_count": str(FULL_SEGMENTS),
            "failed_segment_count": "0",
            "conflict_count": "0",
            "unsafe_entry_count": "0",
            "runtime_full_astar_calls": "0",
            "global_reservation_scan_count": "0",
            "future_routes_stored": "0",
            "unresolved_deadlock_count": "0",
            "event_limit_reached": "False",
            "time_limit_reached": "False",
            "reservation_depth": "1",
            "physical_fault_edge_entry_violation_count": "0",
            "fault_event_count": "0",
            "fault_policy_enabled": "True",
            "physical_interlock_bypass": "False",
            "two_step_reservation_count": "0",
            "priority_teacher_input_count": "0",
            "priority_future_route_input_count": "0",
            "priority_global_scan_count": "0",
            "scorer_teacher_input_count": "0",
            "scorer_future_route_input_count": "0",
            "scorer_future_schedule_input_count": "0",
            "scorer_runtime_global_scan_count": "0",
            "scorer_posthoc_input_count": "0",
        }
        for row in candidate_rows:
            for field, expected in exact_hard_gate_fields.items():
                if row.get(field) != expected:
                    raise JointEvaluationError(
                        f"{candidate_id} committed hard gate drift: "
                        f"{field}={row.get(field)!r}"
                    )
            if (
                row.get("max_edges_selected_per_arrive")
                not in {"0", "1"}
                or row.get("max_edges_selected_per_bag_per_decision")
                not in {"0", "1"}
            ):
                raise JointEvaluationError(
                    f"{candidate_id} committed one-step gate drift"
                )
    binaries = {row["binary_sha256"] for row in repeats}
    sources = {row["source_bundle_sha256"] for row in repeats}
    base_heads = {row["repository_base_head"] for row in repeats}
    if len(binaries) != 1 or len(sources) != 1 or len(base_heads) != 1:
        raise JointEvaluationError(
            "cross-finalist binary/source/base-HEAD drift"
        )
    binary_path = (
        root
        / "build_g4irsf12"
        / "python"
        / "czr005_cpp.cp311-win_amd64.pyd"
    )
    if binaries != {cde.file_sha256(binary_path)}:
        raise JointEvaluationError("committed binary hash is stale")
    current_source_bundle = _source_bundle(root)
    if sources != {current_source_bundle["bundle_sha256"]}:
        raise JointEvaluationError("committed source bundle is stale")
    if bundle.get("source_bundle") != current_source_bundle:
        raise JointEvaluationError("bundle source manifest drift")
    if {row["map_raw_sha256"] for row in repeats} != {
        cde.CANONICAL_MAP_RAW_SHA256
    }:
        raise JointEvaluationError("committed map hash drift")
    if {row["task_raw_sha256"] for row in repeats} != {
        cde.CANONICAL_SOURCE_RAW_SHA256
    }:
        raise JointEvaluationError("committed task hash drift")
    full_selection = cde.load_prefix_selection("full", root)
    if {
        row["input_selection_sha256"] for row in repeats
    } != {full_selection.selected_rows_sha256}:
        raise JointEvaluationError("committed full input selection drift")
    not_run = {
        row["candidate_id"]: row
        for row in rows
        if row.get("row_type") == "FINALIST_NOT_RUN"
    }
    if set(not_run) != {
        "H2_V3_RESIDUAL",
        "H3_V3_RESIDUAL_FAULT_CONTROL_NO_FAULT",
    }:
        raise JointEvaluationError("H2/H3 NOT_RUN rows drift")
    performance_fields = (
        "original_entry_mean_minutes",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
    )
    for row in not_run.values():
        if (
            row.get("execution_status") != "NOT_RUN"
            or row.get("blocker") != V3_BLOCKER
            or any(row.get(field, "") != "" for field in performance_fields)
        ):
            raise JointEvaluationError("H2/H3 NOT_RUN semantics drift")
    slices = [row for row in rows if row.get("row_type") == "SLICE"]
    required_slice_types = {
        "continuous_6h_block",
        "source",
        "goal",
        "clock_hour",
        "busy_hour",
        "ebs_release",
        "contention",
        "storage_lifecycle",
    }
    for candidate_id in (
        "H0_F2_FROZEN",
        "H1_Q1_THESIS_NO_LEARNING",
    ):
        observed = {
            row["slice_type"]
            for row in slices
            if row["candidate_id"] == candidate_id
        }
        if not required_slice_types <= observed:
            raise JointEvaluationError(
                f"{candidate_id} required real-input slices missing"
            )
    for key in (
        "strict_win_vs_v2_safe",
        "strict_win_vs_f2",
        "all_1x_hard_gates_pass",
    ):
        if not isinstance(bundle.get(key), bool):
            raise JointEvaluationError(f"bundle {key} must be boolean")
    if bundle.get("selected_candidate_id") != (
        "H1_Q1_THESIS_NO_LEARNING"
    ):
        raise JointEvaluationError("bundle selected candidate drift")
    if bundle.get("decision_status") != "HISTORICAL_ONLY_PASS":
        raise JointEvaluationError("bundle decision status drift")
    if bundle.get("strict_win_vs_v2_safe") is not False:
        raise JointEvaluationError("unexpected v2-safe strict win")
    if bundle.get("strict_win_vs_f2") is not False:
        raise JointEvaluationError("unexpected F2 strict win")
    if bundle.get("all_1x_hard_gates_pass") is not True:
        raise JointEvaluationError("original-1x hard gates are not all PASS")
    if bundle.get("full_candidate_count") != 2:
        raise JointEvaluationError("full candidate count drift")
    if bundle.get("full_candidate_count", 99) > MAX_FULL_FINALISTS:
        raise JointEvaluationError("full candidate maximum exceeded")
    if bundle.get("experiment_base_head") != next(iter(base_heads)):
        raise JointEvaluationError("experiment base HEAD binding drift")
    if bundle.get("algorithm_equivalence_protocol") != {
        "complete_bags_hash_required": True,
        "junction_state_hash_required": True,
        "full_algorithm_summary_hash_required": True,
        "trace_context_hash_required": True,
        "excluded_nonalgorithm_fields": sorted(
            NONALGORITHM_RUNTIME_FIELDS
        ),
    }:
        raise JointEvaluationError(
            "bundle algorithm-equivalence protocol drift"
        )
    if (
        bundle.get("h2_execution_status") != "NOT_RUN"
        or bundle.get("h2_not_run_reason") != V3_BLOCKER
        or bundle.get("h3_execution_status") != "NOT_RUN"
        or bundle.get("h3_not_run_reason") != V3_BLOCKER
    ):
        raise JointEvaluationError("bundle H2/H3 NOT_RUN semantics drift")
    failed_audit = bundle.get("failed_projection_audit")
    if (
        not isinstance(failed_audit, Mapping)
        or failed_audit.get("status") != "FAILED_PROJECTION_AUDIT"
        or failed_audit.get("reused_for_final_equivalence") is not False
        or failed_audit.get("file_sha256")
        != cde.file_sha256(root / PROJECTION_AUDIT_PATH)
    ):
        raise JointEvaluationError("failed-projection audit binding drift")
    validator_failure_audit = bundle.get(
        "projection_validator_failure_audit"
    )
    if (
        not isinstance(validator_failure_audit, Mapping)
        or validator_failure_audit.get("status")
        != "PROJECTION_VALIDATOR_FAILURE"
        or validator_failure_audit.get("reused_for_final_equivalence")
        is not False
        or validator_failure_audit.get("file_sha256")
        != cde.file_sha256(root / VALIDATOR_FAILURE_AUDIT_PATH)
    ):
        raise JointEvaluationError(
            "projection-validator failure audit binding drift"
        )
    report_encoding_audit = bundle.get(
        "report_encoding_validator_failure_audit"
    )
    if (
        not isinstance(report_encoding_audit, Mapping)
        or report_encoding_audit.get("status")
        != "REPORT_ENCODING_VALIDATOR_FAILURE"
        or report_encoding_audit.get("reused_for_final_equivalence")
        is not False
        or report_encoding_audit.get("file_sha256")
        != cde.file_sha256(root / REPORT_ENCODING_AUDIT_PATH)
    ):
        raise JointEvaluationError(
            "report-encoding failure audit binding drift"
        )
    bundle_repeats = bundle.get("repeat_bindings")
    if not isinstance(bundle_repeats, list) or len(bundle_repeats) != 2:
        raise JointEvaluationError("bundle repeat bindings missing")
    table_by_candidate = {
        candidate_id: [
            row
            for row in repeats
            if row["candidate_id"] == candidate_id
        ]
        for candidate_id in (
            "H0_F2_FROZEN",
            "H1_Q1_THESIS_NO_LEARNING",
        )
    }
    for binding in bundle_repeats:
        if not isinstance(binding, Mapping):
            raise JointEvaluationError("bundle repeat binding is not an object")
        candidate_id = str(binding.get("candidate_id", ""))
        candidate_rows = table_by_candidate.get(candidate_id)
        if candidate_rows is None:
            raise JointEvaluationError("bundle repeat candidate drift")
        first = candidate_rows[0]
        for field in (
            "runtime_deterministic_sha256",
            "bags_sha256",
            "junction_state_sha256",
            "algorithm_summary_sha256",
            "trace_context_sha256",
            "segment_result_sha256",
            "slice_projection_sha256",
            "binary_sha256",
            "source_bundle_sha256",
            "repository_base_head",
            "map_raw_sha256",
            "task_raw_sha256",
            "input_selection_sha256",
        ):
            if str(binding.get(field, "")) != first[field]:
                raise JointEvaluationError(
                    f"bundle/table repeat binding drift: {candidate_id}/{field}"
                )
        if binding.get("repeat_result_file_sha256") != [
            row["repeat_result_file_sha256"] for row in candidate_rows
        ]:
            raise JointEvaluationError(
                f"bundle repeat file binding drift: {candidate_id}"
            )
    output_bindings = bundle.get("output_bindings")
    if not isinstance(output_bindings, Mapping):
        raise JointEvaluationError("bundle output bindings missing")
    if output_bindings.get(TABLE_PATH.as_posix()) != cde.file_sha256(
        table_path
    ):
        raise JointEvaluationError("bundle table hash drift")
    if output_bindings.get(REPORT_PATH.as_posix()) != cde.file_sha256(
        report_path
    ):
        raise JointEvaluationError("bundle report hash drift")
    expected_self = bundle.get("bundle_sha256")
    projection = dict(bundle)
    projection.pop("bundle_sha256", None)
    if expected_self != cde.canonical_sha256(projection):
        raise JointEvaluationError("bundle self hash drift")
    if "HISTORICAL_ONLY_PASS" not in report:
        raise JointEvaluationError("report decision label drift")
    if "4.124305453" not in report or "not used" not in report:
        raise JointEvaluationError("report denominator warning missing")
    validate_v3_fail_closed(root)
    validate_h1_tie_break(root)
    return {
        "status": "PASS",
        "decision_status": bundle["decision_status"],
        "repeat_count": len(repeats),
        "slice_row_count": len(slices),
        "binary_sha256": next(iter(binaries)),
        "source_bundle_sha256": next(iter(sources)),
        "table_sha256": cde.file_sha256(table_path),
        "report_sha256": cde.file_sha256(report_path),
        "bundle_file_sha256": cde.file_sha256(bundle_path),
    }


def run(
    *,
    binary: Path,
    search_path: Path,
    archive_root: Path | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    if len(FINALISTS) > MAX_FULL_FINALISTS:
        raise JointEvaluationError("too many full finalists")
    selection_evidence = dict(validate_h1_tie_break(root))
    selection_evidence["failed_projection_audit"] = (
        bind_failed_projection_audit(root)
    )
    selection_evidence["projection_validator_failure_audit"] = (
        bind_projection_validator_failure_audit(root)
    )
    selection_evidence["report_encoding_validator_failure_audit"] = (
        bind_report_encoding_validator_failure_audit(root)
    )
    v3_dependency = validate_v3_fail_closed(root)
    contention_ids, contention_hash = _contention_task_ids(root)
    from czr005 import cpp_backend

    executor = cpp_backend.g4irsf11_event_runtime_from_records
    # Execute the first H1 full run before spending the remaining full budget.
    # The lower-level function stops immediately on any hard failure.
    results: dict[str, list[dict[str, Any]]] = {}
    h1 = next(row for row in FINALISTS if row.candidate_id.startswith("H1_"))
    h1_rows = execute_finalist_repeats(
        h1,
        executor=executor,
        binary=binary,
        search_path=search_path,
        selection_evidence=selection_evidence,
        v3_dependency=v3_dependency,
        contention_task_ids=contention_ids,
        contention_source_sha256=contention_hash,
        root=root,
        archive_root=archive_root,
    )
    results[h1.candidate_id] = h1_rows
    if len(h1_rows) != REPEAT_COUNT or any(
        row["gate_status"] != "PASS" for row in h1_rows
    ):
        return {
            "status": "STOPPED_ON_H1_HARD_FAILURE",
            "results": results,
            "selection_evidence": selection_evidence,
            "v3_dependency": v3_dependency,
        }
    h0 = next(row for row in FINALISTS if row.candidate_id.startswith("H0_"))
    h0_rows = execute_finalist_repeats(
        h0,
        executor=executor,
        binary=binary,
        search_path=search_path,
        selection_evidence=selection_evidence,
        v3_dependency=v3_dependency,
        contention_task_ids=contention_ids,
        contention_source_sha256=contention_hash,
        root=root,
        archive_root=archive_root,
    )
    results[h0.candidate_id] = h0_rows
    if len(h0_rows) != REPEAT_COUNT or any(
        row["gate_status"] != "PASS" for row in h0_rows
    ):
        return {
            "status": "STOPPED_ON_H0_HARD_FAILURE",
            "results": results,
            "selection_evidence": selection_evidence,
            "v3_dependency": v3_dependency,
        }
    write_result = write_outputs(
        results,
        selection_evidence=selection_evidence,
        v3_dependency=v3_dependency,
        root=root,
    )
    return {
        "status": "COMPLETE",
        "results": results,
        "selection_evidence": selection_evidence,
        "v3_dependency": v3_dependency,
        "write_result": write_result,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--allow-full", action="store_true")
    parser.add_argument("--validate-committed", action="store_true")
    parser.add_argument(
        "--binary",
        type=Path,
        default=ROOT
        / "build_g4irsf12"
        / "python"
        / "czr005_cpp.cp311-win_amd64.pyd",
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        default=ROOT / "build_g4irsf12" / "python",
    )
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args(argv)
    output: dict[str, Any] = {"schema": SCHEMA}
    if args.run:
        if not args.allow_full:
            raise JointEvaluationError(
                "--run requires explicit --allow-full authorization"
            )
        run_result = run(
            binary=args.binary,
            search_path=args.search_path,
            archive_root=args.archive_root,
        )
        output["run"] = {
            "status": run_result["status"],
            "candidate_counts": {
                candidate_id: len(rows)
                for candidate_id, rows in run_result["results"].items()
            },
            "hard_gate_statuses": {
                candidate_id: [row["gate_status"] for row in rows]
                for candidate_id, rows in run_result["results"].items()
            },
            "write_result": run_result.get("write_result", {}),
        }
    if args.validate_committed:
        output["validation"] = validate_committed_outputs()
    if not args.run and not args.validate_committed:
        parser.error("choose --run and/or --validate-committed")
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
