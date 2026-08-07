from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf19_route_campaign as campaign


ROOT = Path(__file__).resolve().parents[1]


def _decision(
    *,
    selected: int,
    candidates: list[int] | None = None,
    segment: str = "seg-1",
    task: int = 1,
    current: int = 1,
    goal: int = 4,
    risk: bool = False,
    shield: bool = False,
) -> dict[str, Any]:
    candidates = candidates or [2, 3]
    return {
        "segment_id": segment,
        "task_id": task,
        "current_node": current,
        "goal_node": goal,
        "candidate_next_nodes": candidates,
        "selected_next": selected,
        "model_prediction": selected,
        "risk_gate_triggered": risk,
        "safety_shield_triggered": shield,
        "metadata": {"scorer_raw_prediction": selected},
    }


def _summary(mode: str, *, trace: bool = True) -> dict[str, Any]:
    return {
        "merge_grant_timing_mode": campaign.J2_TIMING_MODE,
        "scorer_mode": mode,
        "completed_count": 1,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "unresolved_deadlock_count": 0,
        "runtime_full_astar_calls": 0,
        "runtime_full_cie_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "priority_global_scan_count": 0,
        "scorer_runtime_global_scan_count": 0,
        "microphase_runtime_global_scan_count": 0,
        "first_edge_credit_global_scan_count": 0,
        "priority_future_route_input_count": 0,
        "scorer_future_route_input_count": 0,
        "first_edge_credit_future_route_count": 0,
        "scorer_future_schedule_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "event_count": 10,
        "decision_count": 1,
        "loop_count": 0,
        "fairness_jain": 1.0,
        "trace_limit": 500_000 if trace else 0,
        "decision_trace_seen_count": 1 if trace else 0,
        "decision_trace_stored_count": 1 if trace else 0,
        "decision_trace_truncated": False,
        "scorer_decision_evaluation_count": 1,
        "scorer_candidate_evaluation_count": 2,
        "scorer_risk_abstain_count": 0,
        "shield_rejection_count": 0,
        "physical_fault_interlock_rejection_count": 0,
    }


def _payload(mode: str, selected: int) -> dict[str, Any]:
    return {
        "summary": _summary(mode),
        "bags": [
            {
                "segment_id": "seg-1",
                "task_id": 1,
                "release_time": 0.0,
                "admitted_time": 1.0,
                "finish_time": 5.0,
                "junction_queue_wait_seconds": 1.25,
                "merge_grant_wait_seconds": 0.5,
                "completed": True,
            }
        ],
        "decision_trace": [_decision(selected=selected)],
    }


def _input(_: campaign.RouteCase) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return (
        [
            {
                "segment_id": "seg-1",
                "task_id": 1,
                "pass_time": 0.0,
                "original_entry_time": 0.0,
                "std": 10.0,
                "start": 1,
                "goal": 4,
                "source": "node_1",
            }
        ],
        {
            "tth_denominator": "original_entry_time_tth",
            "topology_changed": False,
            "segments": 1,
            "scale": 1,
        },
    )


def test_build_cases_keeps_large_and_scale_cases_trace_free() -> None:
    cases = campaign.build_cases(
        prefixes=(144, 512, 2_048, 8_192),
        evidence_prefixes=(144, 512),
        scales=(1, 2),
    )
    assert [case.case_id for case in cases] == [
        "prefix_144",
        "prefix_512",
        "prefix_2048",
        "prefix_8192",
        "scale_1x",
        "scale_2x",
    ]
    assert [case.telemetry_mode for case in cases] == [
        "evidence_trace",
        "evidence_trace",
        "capacity",
        "capacity",
        "capacity",
        "capacity",
    ]
    with pytest.raises(campaign.RouteCampaignError, match="G18 fixed ladder"):
        campaign.build_cases(prefixes=(256,), evidence_prefixes=())


def test_runtime_request_uses_model_only_for_s1_s2_and_disables_capacity_trace() -> None:
    rows, _ = _input(
        campaign.RouteCase("prefix_144", "prefix", "evidence_trace", 144, 1)
    )
    graph = ([(1, 0, 1.0, 0, 0, [])], [], [[0.0]])
    evidence = campaign.RouteCase("prefix_144", "prefix", "evidence_trace", 144, 1)
    capacity = campaign.RouteCase("prefix_2048", "prefix", "capacity", 2_048, 1)
    binary = Path("build/fake.pyd")
    model = Path("artifacts/fake_model.json")

    for arm_id in ("S1", "S2"):
        request = campaign.build_runtime_request(
            evidence,
            campaign.ARM_BY_ID[arm_id],
            rows=rows,
            graph=graph,
            binary=binary,
            model_path=model,
        )
        assert request["scorer_model_path"] == model
        assert request["trace_limit"] == campaign.DEFAULT_DECISION_TRACE_LIMIT
        assert request["event_trace_limit"] == 0
        assert request["merge_grant_timing_mode"] == campaign.J2_TIMING_MODE
        assert request["merge_grant_rule"] == campaign.J2_MERGE_RULE

    for arm_id in ("S3", "S4"):
        request = campaign.build_runtime_request(
            capacity,
            campaign.ARM_BY_ID[arm_id],
            rows=rows,
            graph=graph,
            binary=binary,
            model_path=model,
        )
        assert "scorer_model_path" not in request
        assert request["trace_limit"] == 0
        assert request["event_trace_limit"] == 0


def test_compact_route_mutations_matches_fifo_same_state_and_reports_fallbacks() -> None:
    baseline = [
        _decision(selected=2),
        _decision(selected=2, segment="seg-2", task=2, risk=True),
        _decision(selected=2, segment="seg-3", task=3, candidates=[2]),
    ]
    treatment = [
        _decision(selected=3),
        _decision(selected=2, segment="seg-2", task=2, shield=True),
        _decision(selected=2, segment="seg-3", task=3, candidates=[2]),
    ]
    result = campaign.compact_route_mutations(baseline, treatment)
    assert result["status"] == "COMPLETE_CAPTURE_SAME_STATE_MATCH"
    assert result["matched_state_rows"] == 3
    assert result["matched_branch_opportunity_rows"] == 2
    assert result["distinct_selected_next_mutation_count"] == 1
    assert result["distinct_selected_next_mutation_rate"] == pytest.approx(0.5)
    assert result["matched_rows_with_risk_fallback"] == 1
    assert result["matched_rows_with_shield_fallback"] == 1
    assert result["baseline"]["branch_opportunity_rows"] == 2
    assert result["treatment"]["configured_scorer_ownership_rows"] == 2

    truncated = campaign.compact_route_mutations(
        baseline, treatment, treatment_truncated=True
    )
    assert truncated["status"] == "OBSERVED_LOWER_BOUND_TRACE_TRUNCATED"
    assert truncated["complete_trace_mutation_upper_bound"] is None


def test_fake_executor_runs_all_native_modes_and_discards_raw_trace() -> None:
    calls: list[Mapping[str, Any]] = []
    selected = {"S1": 2, "S2": 3, "S3": 2, "S4": 3}
    mode_to_id = {arm.scorer_mode: arm.arm_id for arm in campaign.ROUTE_ARMS}

    def fake_executor(request: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(request)
        arm_id = mode_to_id[str(request["scorer_mode"])]
        return _payload(str(request["scorer_mode"]), selected[arm_id])

    case = campaign.RouteCase(
        "prefix_144", "prefix", "evidence_trace", prefix_segments=144
    )
    result = campaign.execute_case(
        case,
        binary=Path("build/fake.pyd"),
        root=ROOT,
        executor=fake_executor,
        input_loader=_input,
        graph=([(1, 0, 1.0, 0, 0, [])], [], [[0.0]]),
    )

    assert result["status"] == "COMPLETE"
    assert len(calls) == 4
    assert "scorer_model_path" in calls[0]
    assert "scorer_model_path" in calls[1]
    assert "scorer_model_path" not in calls[2]
    assert "scorer_model_path" not in calls[3]
    pairs = {row["treatment_arm"]: row for row in result["comparisons"]}
    assert pairs["S2"]["route_mutation"]["distinct_selected_next_mutation_count"] == 1
    assert pairs["S3"]["route_mutation"]["distinct_selected_next_mutation_count"] == 0
    assert pairs["S4"]["route_mutation"]["distinct_selected_next_mutation_count"] == 1
    assert result["arms"]["S1"]["metrics"]["mean_tth_seconds"] == 5.0
    assert result["arms"]["S1"]["metrics"]["source_wait_mean_seconds"] == 1.0
    assert result["arms"]["S1"]["metrics"]["route_wait_mean_seconds"] == 1.25
    serialized = json.dumps(result)
    assert "seg-1" not in serialized
    assert all(
        set(arm_result) == {
            "arm",
            "status",
            "hard_safety",
            "resources",
            "metrics",
            "telemetry",
            "counters",
        }
        for arm_result in result["arms"].values()
    )
    assert result["runtime_contract"]["raw_decision_rows_persisted"] is False


def test_capacity_mutation_is_explicitly_not_collected() -> None:
    result = campaign.compact_route_mutations(
        [], [], telemetry_enabled=False
    )
    assert result["status"] == "NOT_COLLECTED_CAPACITY_MODE"
    assert result["distinct_selected_next_mutation_count"] is None
    assert result["baseline"]["stored_rows"] == 0


def test_case_cache_key_includes_decision_trace_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.touch()
    case = campaign.RouteCase(
        "prefix_144", "prefix", "evidence_trace", prefix_segments=144
    )
    calls: list[int] = []

    def fake_execute_case(
        selected: campaign.RouteCase,
        *,
        decision_trace_limit: int,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        calls.append(decision_trace_limit)
        return {
            "schema": campaign.SCHEMA_CASE_RESULT,
            "case": selected.as_dict(),
            "runtime_contract": {
                "decision_trace_limit": decision_trace_limit,
            },
            "arms": {},
            "comparisons": [],
            "status": "COMPLETE",
        }

    monkeypatch.setattr(campaign, "execute_case", fake_execute_case)
    common = {
        "cases": [case],
        "binary": binary,
        "results_dir": tmp_path / "jobs",
        "json_path": tmp_path / "campaign.json",
        "csv_path": tmp_path / "campaign.csv",
        "report_path": tmp_path / "campaign.md",
    }

    campaign.run_campaign(**common, decision_trace_limit=7)
    campaign.run_campaign(**common, decision_trace_limit=11)
    campaign.run_campaign(**common, decision_trace_limit=11)

    assert calls == [7, 11]
    cached = json.loads(
        (tmp_path / "jobs/g4irsf19_route_prefix_144.json").read_text(
            encoding="utf-8"
        )
    )
    assert cached["runtime_contract"]["decision_trace_limit"] == 11
