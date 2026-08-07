from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import run_g4irsf17_g2_matched_pilot as pilot


def _raw(task_id: int, tth: float, source: float, network: float, block: int) -> dict[str, object]:
    return {
        "task_id": task_id,
        "complete": True,
        "tth_seconds": tth,
        "source_wait_seconds": source,
        "network_time_seconds": network,
        "time_block": block,
    }


def _result(job: pilot.PilotJob, rows: list[dict[str, object]], support: int = 72) -> dict[str, object]:
    return {
        "schema": pilot.SCHEMA_RESULT,
        "evidence_kind": pilot.EVIDENCE_KIND,
        "job": job.as_dict(),
        "status": "COMPLETE",
        "causal_authorization": {
            "authorized": False,
            "same_state_causal_opportunity_count": 0,
            "reason": pilot.CAUSAL_LIMITATION,
        },
        "hard_safety": {"safety_pass": True, "gates": {"safe": True}},
        "telemetry_audit": {
            "telemetry_complete": True,
            "exact_live_eligible_multi_request_boundary_count": support,
        },
        "raw_bags": rows,
    }


def test_plan_is_deterministic_and_never_claims_causal_authorization() -> None:
    first = pilot.build_plan()
    second = pilot.build_plan()
    assert first == second
    assert first["segments"] == [144, 512]
    assert first["rules"] == ["M1", "M2", "M3", "M4", "M5", "M6"]
    assert len(first["jobs"]) == 12
    assert first["causal_authorization"]["authorized"] is False
    assert first["causal_authorization"]["same_state_causal_opportunity_count"] == 0
    assert first["design"]["manipulated_control"] == "merge_grant_rule"
    pilot.validate_plan(first)


def test_native_request_changes_only_rule_and_scenario_between_arms(tmp_path: Path) -> None:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.touch()
    m1 = pilot.PilotJob("g2_s144_m1", 144, "M1", "fifo", 1)
    m6 = pilot.PilotJob("g2_s144_m6", 144, "M6", "thesis_local", 2)
    common = {
        "binary": binary,
        "node_records": [(1, 0.0)],
        "edge_records": [(1, 2, 1.0)],
        "heuristic_time": [(1, 2, 1.0)],
        "bag_records": [("a", 1, 0.0, 10.0, 1, 2, "source")],
        "root": pilot.ROOT,
        "opportunity_trace_limit": 1234,
    }
    left = pilot.build_native_request(job=m1, **common)
    right = pilot.build_native_request(job=m6, **common)
    differing = {key for key in left if left[key] != right[key]}
    assert differing == {"scenario", "merge_grant_rule"}
    assert left["event_semantics"] == "E4_batch_plus_destination_merge_request"
    assert left["g4irsf16_supervisor_mode"] == "off"
    assert left["enable_opportunity_telemetry"] is True
    assert left["opportunity_trace_limit"] == 1234
    assert left["merge_grant_max_pending_requests"] == 256


def test_telemetry_uses_exact_competitive_counter_and_fails_closed_on_drop() -> None:
    rows = [
        {
            "destination_node": 7,
            "known_competing_request_count": 1,
            "later_same_time_competitor_count": 0,
        },
        {
            "destination_node": 7,
            "known_competing_request_count": 0,
            "later_same_time_competitor_count": 0,
        },
    ]
    payload = {
        "summary": {
            "opportunity_telemetry_enabled": True,
            "merge_visibility_total_count": 2,
            "merge_visibility_stored_count": 2,
            "merge_visibility_dropped_count": 0,
            "g4irsf14_i2_live_eligible_multi_request_boundary_count": 72,
        },
        "merge_request_visibility": rows,
    }
    audit = pilot._telemetry_audit(payload)
    assert audit["telemetry_complete"] is True
    assert audit["merge_visibility_competitive_row_count"] == 1
    assert audit["exact_live_eligible_multi_request_boundary_count"] == 72

    payload["summary"]["merge_visibility_total_count"] = 3
    payload["summary"]["merge_visibility_dropped_count"] = 1
    audit = pilot._telemetry_audit(payload)
    assert audit["merge_visibility_count_identity"] is True
    assert audit["telemetry_complete"] is False
    assert audit["exact_live_eligible_multi_request_boundary_count"] == 72


def test_analysis_pairs_against_m1_but_keeps_promotion_closed(tmp_path: Path) -> None:
    plan = pilot.build_plan(
        segments=(144,),
        rules=("M1", "M2"),
        bootstrap_replicates=200,
    )
    jobs = [pilot.PilotJob.from_mapping(row) for row in plan["jobs"]]
    m1, m2 = jobs
    baseline = [
        _raw(1, 10.0, 4.0, 6.0, 0),
        _raw(2, 20.0, 8.0, 12.0, 1),
    ]
    candidate = [
        _raw(1, 8.0, 3.0, 5.0, 0),
        _raw(2, 18.0, 7.0, 11.0, 1),
    ]
    for job, rows in ((m1, baseline), (m2, candidate)):
        path = tmp_path / f"{job.job_id}.json"
        path.write_text(json.dumps(_result(job, rows)), encoding="utf-8")

    analysis = pilot.analyse_plan(plan, results_dir=tmp_path, root=tmp_path)
    assert analysis["status"] == "COMPLETE_MATCHED_SCREEN"
    assert analysis["causal_authorization"]["authorized"] is False
    assert analysis["causal_authorization"]["same_state_causal_opportunity_count"] == 0
    comparison = analysis["comparisons"][0]
    assert comparison["candidate_rule"] == "M2"
    assert comparison["performance"]["mean_tth_delta_seconds"] == -2.0
    assert comparison["performance"]["source_wait_delta_mean_seconds"] == -1.0
    assert comparison["performance"]["network_time_delta_mean_seconds"] == -1.0
    assert comparison["timing_decomposition_reconciles"] is True
    assert comparison["matched_support_gate_64_pass"] is True
    assert comparison["promotion_authorized"] is False
    assert analysis["recommended_for_same_state_causal_followup"][0]["rule"] == "M2"


def test_run_checkpoints_errors_as_retryable_and_never_authorizes(tmp_path: Path) -> None:
    plan = pilot.build_plan(segments=(144,), rules=("M1",), bootstrap_replicates=100)

    def broken(job: pilot.PilotJob, **_: object) -> dict[str, object]:
        raise RuntimeError(f"native failed for {job.job_id}")

    run = pilot.run_plan(
        plan,
        binary=tmp_path / "missing.pyd",
        results_dir=tmp_path,
        root=tmp_path,
        executor=broken,
    )
    assert run["complete"] is False
    assert run["failed_job_ids"] == ["g2_s144_m1"]
    result = json.loads((tmp_path / "g2_s144_m1.json").read_text(encoding="utf-8"))
    assert result["status"] == "ERROR"
    assert result["error"]["retryable"] is True
    assert result["causal_authorization"]["authorized"] is False


def test_parser_exposes_plan_run_analyse_and_all() -> None:
    help_text = pilot._parser().format_help()
    assert "plan" in help_text
    assert "run" in help_text
    assert "analyse" in help_text
    assert "all" in help_text
