from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil

from scripts.eval import g4irsf12_calibrated_scale_frontier as frontier


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _candidate_bundle(*, passed: bool) -> dict[str, object]:
    finalist = {
        "candidate_id": "J_F1",
        "case_id": "J_F1_best_rule_bounded_pibt",
        "config_sha256": "a" * 64,
        "deterministic_result_sha256": "b" * 64 if passed else "",
        "executed_full_repeat_count": 5 if passed else 0,
        "repeat_gate": "PASS" if passed else "PENDING",
        "v2_safe_original_entry_gate": "PASS" if passed else "PENDING",
        "corrected_hca_original_entry_gate": "PASS" if passed else "PENDING",
        "validated_full_gate": "PASS" if passed else "PENDING",
        "promotion_status": "PROMOTED" if passed else "PENDING",
        "blocker": "" if passed else "requires at least five full repeats",
    }
    bundle: dict[str, object] = {
        "schema": frontier.J_BUNDLE_SCHEMA,
        "g4j_enabled": False,
        "g4j_status": "CLOSED",
        "phase_j_promotion_opens_g4j": False,
        "promotion_status": "READY" if passed else "PENDING",
        "primary_denominator": "original_entry_time_tth",
        "finalists": [finalist],
    }
    bundle["bundle_sha256"] = frontier.canonical_sha256(bundle)
    return bundle


def _k_protocol(*, calibrated: bool, traceable: bool) -> dict[str, object]:
    phase_l_pass = calibrated and traceable
    return {
        "schema": frontier.K_PROTOCOL_SCHEMA,
        "published_date": "2026-07-23",
        "baseline": {
            "bag_count": frontier.BASELINE_BAGS,
            "segment_count": frontier.BASELINE_SEGMENTS,
        },
        "calibration": {
            "calibrated_multiplier": 1.3 if calibrated else None,
            "calibrated_multiplier_status": "PASS" if calibrated else "UNKNOWN_NOT_COMPUTABLE",
            "finite_uncertainty_interval": [1.2, 1.4] if calibrated else None,
            "phase_k_status": "PASS" if calibrated else "PARTIAL_WITH_EXPLICIT_BLOCKER",
        },
        "candidate_scales": [
            {
                "scale_id": scale_id,
                "nominal_multiplier": multiplier,
                "classification": classification,
            }
            for scale_id, multiplier, classification, _, _ in frontier.SCALES
        ],
        "phase_l_gates": {
            "original_1x_full_formal_pass": phase_l_pass,
            "original_entry_mean_meets_historical_hca_target": phase_l_pass,
            "numeric_real_demand_calibration_complete": calibrated,
            "original_task_generation_audit_pass": True,
            "traceable_1p1_workload_artifact_exists": traceable,
            "protected_map_identity_matches": True,
            "all_gates_pass": phase_l_pass,
            "status": "PASS" if phase_l_pass else frontier.BLOCKED,
        },
        "protected_identity": {
            "map_path": frontier.MAP_PATH.as_posix(),
            "map_raw_sha256": frontier.MAP_RAW_SHA256,
            "map_semantic_sha256": frontier.MAP_SEMANTIC_SHA256,
        },
        "future_generation_protocol": {
            "current_state": (
                "MATERIALIZED_AUDITED" if traceable else "DESCRIPTOR_ONLY_NOT_EXECUTED"
            )
        },
        "execution_policy": (
            "SEQUENTIAL_SCALE_EXECUTION_AUTHORIZED"
            if phase_l_pass
            else "DESCRIPTORS_ONLY_NO_SCALING_RUN"
        ),
    }


def _one_p_one(
    root: Path,
    *,
    materialized: bool,
) -> dict[str, object]:
    state: dict[str, object] = {
        "candidate_workload_materialized": False,
        "runtime_executed": False,
        "execution_authorized": False,
        "workload_generation_level": "descriptor_only_not_generated",
        "task_output_path": None,
    }
    if materialized:
        task_path = root / "artifacts" / "local-cache" / "audited_1p1.jsonl"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text('{"fixture":"not-generated-by-evaluator"}\n', encoding="utf-8")
        state.update(
            {
                "candidate_workload_materialized": True,
                "execution_authorized": True,
                "workload_generation_level": "original_rule_replay_scaled_input",
                "task_output_path": task_path.relative_to(root).as_posix(),
                "task_output_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema": frontier.K_CANDIDATE_SCHEMA,
        "phase": "G4IRSF12-K",
        "scale_id": "1p1",
        "nominal_multiplier": "1.1",
        "artifact_state": state,
    }


def _fixture_root(
    root: Path,
    *,
    j_passed: bool = False,
    calibrated: bool = False,
    materialized_1p1: bool = False,
) -> Path:
    map_path = root / frontier.MAP_PATH
    map_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / frontier.MAP_PATH, map_path)
    _write_json(root / frontier.J_BUNDLE_PATH, _candidate_bundle(passed=j_passed))
    _write_json(
        root / frontier.K_PROTOCOL_PATH,
        _k_protocol(calibrated=calibrated, traceable=materialized_1p1),
    )
    _write_json(
        root / frontier.K_1P1_PATH,
        _one_p_one(root, materialized=materialized_1p1),
    )
    return root


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_current_unknown_calibration_writes_four_blocked_outputs_only(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    tasks_before = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root / "artifacts" / "tasks").rglob("*")
        if path.is_file()
    }

    evaluation = frontier.run(root)

    assert evaluation.status == frontier.BLOCKED
    assert evaluation.calibration_status == "UNKNOWN_NOT_COMPUTABLE"
    assert any("UNKNOWN_NOT_COMPUTABLE" in value for value in evaluation.blockers)
    assert any("descriptor" in value for value in evaluation.blockers)
    outputs = (
        frontier.FRONTIER_REPORT,
        frontier.FRONTIER_TABLE,
        frontier.BACKLOG_TABLE,
        frontier.CLAIM_REPORT,
    )
    assert all((root / path).is_file() for path in outputs)
    rows = _rows(root / frontier.FRONTIER_TABLE)
    assert [row["nominal_multiplier"] for row in rows] == [
        scale[1] for scale in frontier.SCALES
    ]
    assert all(row["execution_status"] == frontier.BLOCKED for row in rows)
    assert all(row["workload_materialized_by_phase_l"] == "False" for row in rows)
    assert all(row["runtime_executed"] == "False" for row in rows)
    backlog = _rows(root / frontier.BACKLOG_TABLE)
    assert len(backlog) == 6
    assert all(row["measurement_status"] == frontier.NOT_MEASURED for row in backlog)
    assert all(row["post_peak_backlog_clearance_seconds"] == "" for row in backlog)
    tasks_after = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root / "artifacts" / "tasks").rglob("*")
        if path.is_file()
    }
    assert tasks_after == tasks_before


def test_phase_j_pass_cannot_override_unknown_phase_k_calibration(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path, j_passed=True)

    evaluation = frontier.evaluate(root)

    assert evaluation.gates["phase_j_original_1x_full_pass"]
    assert not evaluation.gates["numeric_real_demand_calibration_complete"]
    assert evaluation.status == frontier.BLOCKED
    assert evaluation.frontier_rows[0]["execution_authorized"] is False


def test_bundle_self_hash_tamper_fails_closed(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        j_passed=True,
        calibrated=True,
        materialized_1p1=True,
    )
    bundle_path = root / frontier.J_BUNDLE_PATH
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["promotion_status"] = "PENDING"
    _write_json(bundle_path, bundle)

    evaluation = frontier.evaluate(root)

    assert evaluation.status == frontier.BLOCKED
    assert any("self-hash" in value for value in evaluation.blockers)


def test_nonmaterialized_1p1_descriptor_blocks_even_with_numeric_multiplier(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path, j_passed=True, calibrated=True)

    evaluation = frontier.evaluate(root)

    assert evaluation.status == frontier.BLOCKED
    assert not evaluation.gates["traceable_1p1_workload_artifact_exists"]
    assert any("non-materialized descriptor" in value for value in evaluation.blockers)


def test_full_gate_only_authorizes_1p0_repeat_and_runs_nothing(
    tmp_path: Path,
) -> None:
    root = _fixture_root(
        tmp_path,
        j_passed=True,
        calibrated=True,
        materialized_1p1=True,
    )

    evaluation = frontier.run(root)

    assert evaluation.status == frontier.READY
    assert all(evaluation.gates.values())
    assert evaluation.frontier_rows[0]["execution_status"] == frontier.AUTHORIZED
    assert evaluation.frontier_rows[0]["execution_authorized"] is True
    assert all(
        row["execution_status"] == frontier.PREDECESSOR_BLOCKED
        for row in evaluation.frontier_rows[1:]
    )
    assert all(row["runtime_executed"] is False for row in evaluation.frontier_rows)


def test_outputs_are_deterministic_for_identical_input_snapshots(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    output_paths = (
        frontier.FRONTIER_REPORT,
        frontier.FRONTIER_TABLE,
        frontier.BACKLOG_TABLE,
        frontier.CLAIM_REPORT,
    )

    frontier.run(root)
    first = {path: (root / path).read_bytes() for path in output_paths}
    frontier.run(root)
    second = {path: (root / path).read_bytes() for path in output_paths}

    assert first == second
