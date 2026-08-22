from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.eval import finalize_g4irsf25_decision as finalizer


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _policy(mode: str) -> dict[str, Any]:
    return {
        "schema": finalizer.POLICY_SCHEMA,
        "mode": mode,
        "feature_names": [f"f{index}" for index in range(21)],
        "arms": [],
    }


def _counters() -> dict[str, int]:
    return {
        "runtime_global_scans": 0,
        "future_route_inputs": 0,
        "full_astar_calls": 0,
    }


def _screen_row(mode: str, size: int) -> dict[str, Any]:
    active = mode != "off"
    return {
        "schema": finalizer.NATIVE_SCHEMA,
        "mode": mode,
        "arm": finalizer.MODE_LABELS[mode],
        "workload": f"prefix_{size}",
        "execution_mode": "screen_full",
        "scale": 1,
        "repeat": 0,
        "bounded_wall_seconds": finalizer.NOT_MEASURED,
        "evidence_status": "MEASURED_COMPLETE",
        "safety_pass": True,
        "committed_mutations": 1 if active else 0,
        "fallbacks": 1 if active else 0,
        "g25_counters": _counters(),
    }


def _full_row(
    mode: str,
    scale: int,
    repeat: int,
    metrics: tuple[float, float, float, float],
    *,
    mutations: int,
) -> dict[str, Any]:
    requested = 100 if scale == 1 else 200
    return {
        "schema": finalizer.NATIVE_SCHEMA,
        "mode": mode,
        "arm": finalizer.MODE_LABELS[mode],
        "workload": f"scale_{scale}x",
        "execution_mode": "full",
        "scale": scale,
        "repeat": repeat,
        "bounded_wall_seconds": finalizer.NOT_MEASURED,
        "status": "COMPLETE",
        "evidence_status": "MEASURED_COMPLETE",
        "segments_requested": requested,
        "segments_completed": requested,
        "segments_failed": 0,
        "raw_bags_completed": requested // 2,
        "deadline_miss_count": 0,
        "proposals": mutations * 2,
        "committed_mutations": mutations,
        "processed_attempt_mean_seconds": metrics[0],
        "processed_attempt_p95_seconds": metrics[1],
        "processed_attempt_p99_seconds": metrics[2],
        "processed_attempt_max_seconds": metrics[3],
        "safety_pass": True,
        "g25_counters": _counters(),
    }


def _bounded_row(mode: str, duration: float, *, candidate: bool) -> dict[str, Any]:
    baseline_completed = 1000 if duration == 60.0 else 2000
    baseline_backlog = 500 if duration == 60.0 else 400
    return {
        "schema": finalizer.NATIVE_SCHEMA,
        "mode": mode,
        "arm": finalizer.MODE_LABELS[mode],
        "workload": f"scale_4x_{duration:g}s",
        "execution_mode": "bounded",
        "scale": 4,
        "repeat": 0 if duration == 60.0 else 1,
        "bounded_wall_seconds": duration,
        "status": "BOUNDED_PROGRESS",
        "evidence_status": "MEASURED_BOUNDED_PROGRESS",
        "segments_requested": 4000,
        "segments_released": baseline_completed + 500,
        "segments_completed": baseline_completed + (10 if candidate else 0),
        "current_backlog": baseline_backlog - (10 if candidate else 0),
        "events_per_completed_segment": 10.2 if candidate else 10.0,
        "committed_mutations": 20 if candidate else 0,
        "safety_pass": True,
        "g25_counters": _counters(),
    }


def _native_document(profile: str) -> dict[str, Any]:
    s4 = {
        1: (210.0, 247.0, 254.0, 407.0),
        2: (283.0, 512.0, 1284.0, 5511.0),
    }
    t0 = {
        1: (210.01, 247.01, 254.01, 408.0),
        2: (279.0, 500.0, 1270.0, 5500.0),
    }
    l1 = {
        1: (210.0, 247.0, 254.0, 408.0),
        2: (277.0, 495.0, 1260.0, 5490.0),
    }
    if profile in {"t0_only", "no_winner"}:
        l1[2] = (284.0, 513.0, 1285.0, 5600.0)
    if profile == "no_winner":
        t0[2] = (284.0, 513.0, 1285.0, 5600.0)

    rows: list[dict[str, Any]] = []
    for mode in ("off", "t0", "l1"):
        for size in (144, 512, 8192):
            rows.append(_screen_row(mode, size))
    for mode, metrics_by_scale in (("off", s4), ("t0", t0), ("l1", l1)):
        for scale in (1, 2):
            for repeat in (0, 1):
                rows.append(
                    _full_row(
                        mode,
                        scale,
                        repeat,
                        metrics_by_scale[scale],
                        mutations=0 if mode == "off" or scale == 1 else 20,
                    )
                )
        for duration in (60.0, 180.0):
            rows.append(_bounded_row(mode, duration, candidate=mode != "off"))
    return {"schema": finalizer.NATIVE_SCHEMA, "runs": rows}


def _audit(mode: str) -> dict[str, Any]:
    groups = [
        {
            "group_id": f"group-{index:03d}",
            "horizon": "H_system",
            "same_state_start": True,
            "action_changed": True,
            "changed_action_count": 1,
            "branch_node": 10 + index % 2,
            "first_edge": 20 + index % 2,
            "pair_complete": True,
            "horizon_complete": True,
            "raw_bag_comparison_eligible": True,
            "safety_pass": True,
            "runtime_global_scan_count": 0,
            "future_route_input_count": 0,
            "full_astar_call_count": 0,
            "system_mean_delta_seconds": -0.02,
            "system_p95_delta_seconds": -0.01,
            "system_p99_delta_seconds": -0.005,
            "system_max_delta_seconds": 0.5,
            "current_bag_added_delay_seconds": 10.0,
            "deadline_miss_delta": 0,
        }
        for index in range(64)
    ]
    return {
        "schema": finalizer.AUDIT_SCHEMA,
        "candidate_mode": mode,
        "groups": groups,
        "no_fault_full": {
            "status": "MEASURED",
            "full_population_complete": True,
            "safety_pass": True,
            "runtime_global_scan_count": 0,
            "future_route_input_count": 0,
            "full_astar_call_count": 0,
        },
        "fault": {
            "status": "MEASURED",
            "target_count": 2,
            "target_branch_arms": [
                {"branch_node": 10, "first_edge": 20},
                {"branch_node": 11, "first_edge": 21},
            ],
            "exact_s4_fallback_count": 2,
            "lease_recovery_count": 2,
            "physical_fault_edge_entry_violation_count": 0,
            "runtime_global_scan_count": 0,
            "future_route_input_count": 0,
            "full_astar_call_count": 0,
            "safety_pass": True,
        },
    }


def _write_hca(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "evidence_id",
        "scale",
        "evidence_kind",
        "execution_status",
        "released_segment_count",
        "completed_segment_count",
        "canonical_complete_raw_bag_count",
        "canonical_incomplete_raw_bag_count",
        "full_population_tth",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "evidence_id": f"fresh-{scale}x",
                    "scale": scale,
                    "evidence_kind": "FRESH_LOCAL_RUN",
                    "execution_status": "COMPLETE",
                    "released_segment_count": 200 * scale,
                    "completed_segment_count": 190 * scale,
                    "canonical_complete_raw_bag_count": 90 * scale,
                    "canonical_incomplete_raw_bag_count": 10 * scale,
                    "full_population_tth": finalizer.NOT_MEASURED,
                }
                for scale in (2, 4)
            ]
        )


def _fixture(
    root: Path,
    *,
    profile: str = "learning",
    audit_mode: str | None = None,
    omit: str | None = None,
    stale_l2: bool = False,
) -> None:
    documents: dict[str, Mapping[str, Any]] = {
        "g24": {
            "schema": finalizer.G24_SCHEMA,
            "final": {"fresh_hca_beaten": True},
            "reconvergent_corridor": {"status": "MEASURED_NO_GO"},
        },
        "coverage": {
            "schema": finalizer.COVERAGE_SCHEMA,
            "status": "MEASURED",
            "measured_scales": [1, 2],
            "trajectory_count": 128,
            "observed_registered_arm_fraction": 1.0,
            "unsafe_count": 0,
            "loop_count": 0,
        },
        "short_horizon": {
            "schema": finalizer.SHORT_SCHEMA,
            "status": "TARGET_MET",
            "complete_checkpoint_count": 128,
            "complete_checkpoint_count_by_scale": {"1": 64, "2": 64},
            "unsafe_arm_count": 0,
            "ceilings": {
                "full_state": {
                    "mean_possible_improvement_fraction": 0.02,
                    "useful_opportunities": 120,
                    "stable_action_reversal_branch_count": 2,
                },
                "local_observation": {
                    "pairwise_ranking_ceiling": 0.80,
                    "s4_action_accuracy": 0.55,
                },
                "opportunity_mass": 12.0,
            },
        },
        "learning": {
            "l2_trigger": {"triggered": False, "reasons": []},
            "l3_trigger": {"triggered": False, "reasons": []},
            "metrics": {
                "t0_test": {
                    "checkpoint_count": 24,
                    "safety_failure_count": 0,
                    "pairwise_ranking_accuracy": 0.60,
                },
                "l1_test": {
                    "checkpoint_count": 24,
                    "safety_failure_count": 0,
                    "pairwise_ranking_accuracy": 0.70,
                },
            },
        },
        "native": _native_document(profile),
    }
    for name, value in documents.items():
        if omit != name:
            _write_json(root / finalizer.INPUT_PATHS[name], value)
    for mode in ("t0", "l1"):
        if omit != mode:
            _write_json(root / finalizer.POLICY_PATHS[mode], _policy(mode))
    if stale_l2:
        _write_json(
            root / finalizer.POLICY_PATHS["l2"],
            {"schema": "stale.invalid.schema", "mode": "l2"},
        )
    if omit != "hca":
        _write_hca(root / finalizer.INPUT_PATHS["hca"])
    if audit_mode is not None:
        _write_json(root / finalizer.INPUT_PATHS["causal_fault"], _audit(audit_mode))


def _selection(root: Path) -> dict[str, Any]:
    return json.loads((root / finalizer.OUTPUT_PATHS["selection"]).read_text(encoding="utf-8"))


def test_learning_winner_remains_s4_until_final_audit(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="learning")

    summary = finalizer.finalize(tmp_path)
    selection = _selection(tmp_path)

    assert summary["native"]["provisional_winner_candidate_id"] == "L1"
    assert summary["native"]["learning_additive"] is True
    assert len(summary["questions"]) == 28
    assert summary["final_audit"]["status"] == "NOT_MEASURED_FINAL_AUDIT_PENDING"
    assert selection["status"] == "FINAL_AUDIT_REQUIRED"
    assert selection["active_policy"] == "S4"
    assert selection["provisional_candidate_id"] == "L1"
    assert selection["decision"] == finalizer.NOT_MEASURED


def test_t0_only_winner_promotes_after_complete_audit(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="t0_only", audit_mode="t0")

    summary = finalizer.finalize(tmp_path)
    selection = _selection(tmp_path)

    assert summary["native"]["candidates"]["l1"]["eligibility"] == finalizer.FAIL
    assert summary["final_audit"]["status"] == finalizer.PASS
    assert selection["active_policy"] == "T0"
    assert selection["threshold_promoted"] is True
    assert selection["learning_promoted"] is False
    assert selection["decision"] == "LOAD_CONDITIONAL_DECENTRALIZED_THRESHOLD_PROMOTED_LEARNING_NOT_ADDITIVE"


def test_complete_no_winner_keeps_s4_and_reports_audit_na(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="no_winner")

    summary = finalizer.finalize(tmp_path)
    selection = _selection(tmp_path)

    assert summary["native"]["core_state"] == finalizer.PASS
    assert selection["active_policy"] == "S4"
    assert selection["decision"] == "DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE"
    assert summary["final_audit"]["status"] == "NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER"
    assert summary["final_audit"]["complete_group_count"] == finalizer.NOT_MEASURED
    report = (tmp_path / finalizer.OUTPUT_PATHS["causal_report"]).read_text(encoding="utf-8")
    assert "not observed zeros" in report


def test_github_questions_track_g24_and_g25_independently(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="no_winner")
    github_path = tmp_path / finalizer.INPUT_PATHS["github"]
    _write_json(
        github_path,
        {
            "schema": "czr005.g4irsf25.github_status.v1",
            "g24": {"status": "MEASURED", "pr": 9, "run": 73},
            "g25": finalizer.NOT_MEASURED,
        },
    )

    summary = finalizer.finalize(tmp_path)
    assert summary["questions"][0]["status"] == "MEASURED"
    assert summary["questions"][1]["status"] == finalizer.NOT_MEASURED
    assert "github_g24_status" not in summary["not_measured"]
    assert "github_g25_status" in summary["not_measured"]

    _write_json(
        github_path,
        {
            "schema": "czr005.g4irsf25.github_status.v1",
            "g24": {"status": "MEASURED", "pr": 9, "run": 73},
            "g25": {"status": "MEASURED", "branch": "codex/g4irsf25-execution"},
        },
    )
    summary = finalizer.finalize(tmp_path)
    assert summary["questions"][1]["status"] == "MEASURED"
    assert "github_g25_status" not in summary["not_measured"]


def test_missing_core_evidence_is_not_a_failed_or_na_gate(tmp_path: Path) -> None:
    _fixture(tmp_path, omit="coverage")

    summary = finalizer.finalize(tmp_path)
    selection = _selection(tmp_path)

    assert summary["inputs"]["coverage_1x_2x"] == finalizer.NOT_MEASURED
    assert selection["status"] == "INCOMPLETE_EVIDENCE"
    assert selection["decision"] == finalizer.NOT_MEASURED
    assert summary["final_audit"]["status"] == "NOT_MEASURED_CANDIDATE_SELECTION_INCOMPLETE"


def test_stale_l2_is_ignored_when_trigger_is_false(tmp_path: Path) -> None:
    _fixture(tmp_path, stale_l2=True)

    summary = finalizer.finalize(tmp_path)

    assert summary["offline"]["artifact_states"]["l2"] == "NOT_APPLICABLE_NOT_TRIGGERED"
    assert "l2" not in summary["native"]["candidates"]
    assert summary["native"]["core_state"] == finalizer.PASS
    assert summary["native"]["provisional_winner_candidate_id"] == "L1"


def test_missing_required_s4_4x_window_keeps_decision_incomplete(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="no_winner")
    native_path = tmp_path / finalizer.INPUT_PATHS["native"]
    native = json.loads(native_path.read_text(encoding="utf-8"))
    native["runs"] = [
        row
        for row in native["runs"]
        if not (
            row["mode"] == "off"
            and row["execution_mode"] == "bounded"
            and row["bounded_wall_seconds"] == 180.0
        )
    ]
    _write_json(native_path, native)

    summary = finalizer.finalize(tmp_path)

    assert summary["inputs"]["s4_4x_60_180"] == finalizer.NOT_MEASURED
    assert summary["native"]["core_state"] == finalizer.NOT_MEASURED
    assert summary["final"]["status"] == "INCOMPLETE_EVIDENCE"
    assert summary["final"]["decision"] == finalizer.NOT_MEASURED


def test_not_measured_screen_is_incomplete_not_a_measured_rejection(tmp_path: Path) -> None:
    _fixture(tmp_path)
    native_path = tmp_path / finalizer.INPUT_PATHS["native"]
    native = json.loads(native_path.read_text(encoding="utf-8"))
    screen = next(
        row
        for row in native["runs"]
        if row["mode"] == "t0" and row["workload"] == "prefix_144"
    )
    screen["evidence_status"] = finalizer.NOT_MEASURED
    screen["safety_pass"] = finalizer.NOT_MEASURED
    screen["g25_counters"] = {
        name: finalizer.NOT_MEASURED for name in finalizer.FORBIDDEN_COUNTERS
    }
    _write_json(native_path, native)

    summary = finalizer.finalize(tmp_path)

    candidate = summary["native"]["candidates"]["t0"]
    assert candidate["screen"]["status"] == finalizer.NOT_MEASURED
    assert candidate["evidence_completeness"] == finalizer.NOT_MEASURED
    assert summary["final"]["status"] == "INCOMPLETE_EVIDENCE"


def test_hca_error_rows_are_not_measured_capacity() -> None:
    rows = [
        {
            "evidence_id": f"error-{scale}x",
            "scale": str(scale),
            "evidence_kind": "FRESH_LOCAL_RUN",
            "execution_status": "ERROR",
            "released_segment_count": "",
            "completed_segment_count": "",
            "canonical_complete_raw_bag_count": "",
            "canonical_incomplete_raw_bag_count": "",
        }
        for scale in (2, 4)
    ]

    summary = finalizer._summarize_hca(rows)

    assert summary["status"] == finalizer.NOT_MEASURED
    assert summary["scales"]["2"]["status"] == finalizer.NOT_MEASURED
    assert summary["scales"]["4"]["status"] == finalizer.NOT_MEASURED


def test_partial_final_audit_remains_pending(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="t0_only", audit_mode="t0")
    audit_path = tmp_path / finalizer.INPUT_PATHS["causal_fault"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.pop("no_fault_full")
    audit.pop("fault")
    _write_json(audit_path, audit)

    summary = finalizer.finalize(tmp_path)

    assert summary["final_audit"]["status"] == finalizer.NOT_MEASURED
    assert summary["final"]["status"] == "FINAL_AUDIT_REQUIRED"
    assert summary["final"]["active_policy"] == "S4"


def test_hsystem_locality_violation_blocks_promotion(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="t0_only", audit_mode="t0")
    audit_path = tmp_path / finalizer.INPUT_PATHS["causal_fault"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["groups"][0]["runtime_global_scan_count"] = 1
    _write_json(audit_path, audit)

    summary = finalizer.finalize(tmp_path)

    assert summary["final_audit"]["gates"]["coverage_and_integrity"] == finalizer.FAIL
    assert summary["final_audit"]["status"] == finalizer.FAIL
    assert summary["final"]["active_policy"] == "S4"


def test_fault_must_cover_every_changed_branch_arm(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="t0_only", audit_mode="t0")
    audit_path = tmp_path / finalizer.INPUT_PATHS["causal_fault"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["fault"]["target_count"] = 1
    audit["fault"]["target_branch_arms"] = [
        {"branch_node": 10, "first_edge": 20}
    ]
    audit["fault"]["exact_s4_fallback_count"] = 1
    audit["fault"]["lease_recovery_count"] = 1
    _write_json(audit_path, audit)

    summary = finalizer.finalize(tmp_path)

    assert summary["final_audit"]["changed_branch_arm_count"] == 2
    assert summary["final_audit"]["fault"]["status"] == finalizer.FAIL
    assert summary["final"]["active_policy"] == "S4"


def test_schema_failure_does_not_overwrite_any_published_output(tmp_path: Path) -> None:
    _fixture(tmp_path, profile="no_winner")
    assert finalizer.main(["--root", str(tmp_path)]) == 0
    before = {
        name: (tmp_path / relative).read_bytes()
        for name, relative in finalizer.OUTPUT_PATHS.items()
    }
    native_path = tmp_path / finalizer.INPUT_PATHS["native"]
    native = json.loads(native_path.read_text(encoding="utf-8"))
    native["schema"] = "invalid.schema"
    _write_json(native_path, native)

    assert finalizer.main(["--root", str(tmp_path)]) == 2
    after = {
        name: (tmp_path / relative).read_bytes()
        for name, relative in finalizer.OUTPUT_PATHS.items()
    }
    assert after == before
    assert not list(tmp_path.rglob("*.tmp"))


def test_mid_publish_failure_never_changes_selection_authority(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _fixture(tmp_path, profile="no_winner")
    assert finalizer.main(["--root", str(tmp_path)]) == 0
    selection_path = tmp_path / finalizer.OUTPUT_PATHS["selection"]
    selection_before = selection_path.read_bytes()
    real_replace = finalizer.os.replace
    replace_count = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("simulated publish interruption")
        real_replace(source, target)

    monkeypatch.setattr(finalizer.os, "replace", fail_second_replace)

    assert finalizer.main(["--root", str(tmp_path)]) == 2
    assert selection_path.read_bytes() == selection_before
    assert not list(tmp_path.rglob("*.tmp"))
