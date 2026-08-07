from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf18_jit_campaign as campaign


def test_plan_keeps_eager_fifo_and_fair_jit_matched() -> None:
    plan = campaign.build_plan(prefixes=(144, 512), full_scales=(2,))
    validated = campaign.validate_plan(plan)
    assert len(validated["jobs"]) == 9
    assert [row["variant_id"] for row in validated["jobs"][:3]] == [
        "J0_F2_EAGER",
        "J1_F2_JIT_FIFO",
        "J2_F2_JIT_FAIR_AGING_DEADLINE",
    ]
    assert validated["design"]["score_only_is_not_control"] is True


def test_plan_rejects_prefix_scale_confusion() -> None:
    plan = campaign.build_plan(prefixes=(144,), full_scales=())
    plan["jobs"][0]["scale"] = 2
    with pytest.raises(campaign.G18JitCampaignError, match="prefix jobs"):
        campaign.validate_plan(plan)


def _result(job: campaign.Job, *, multi: int, competition: int, mutation: int, shift: float) -> dict:
    raw_bags = [
        {
            "task_id": index,
            "complete": True,
            "tth_seconds": 100.0 + index + shift,
            "source_wait_seconds": 20.0 + shift,
            "network_time_seconds": 80.0 + index,
        }
        for index in range(4)
    ]
    return {
        "schema": campaign.SCHEMA_RESULT,
        "job": job.as_dict(),
        "status": "COMPLETE",
        "hard_safety": {"pass": True, "gates": {}},
        "metrics": {
            "mean_tth_seconds": 101.5 + shift,
            "p95_tth_seconds": 102.85 + shift,
            "p99_tth_seconds": 102.97 + shift,
            "source_wait_mean_seconds": 20.0 + shift,
            "network_time_mean_seconds": 81.5,
            "events_per_completed_segment": 10.0 - mutation,
        },
        "resources": {"wall_seconds": 1.0, "cpu_seconds": 0.5},
        "counters": {
            "event_count": 1_440,
            "merge_grant_service_opportunity_count": 20,
            "merge_grant_multi_candidate_opportunity_count": multi,
            "merge_grant_true_competition_count": competition,
            "merge_grant_order_mutation_count": mutation,
            "merge_grant_peak_pending_requests": 3,
            "merge_grant_wakeup_scheduled_count": 20,
            "merge_grant_wakeup_coalesced_count": 7,
            "merge_grant_stale_wakeup_count": 0,
        },
        "raw_bags": raw_bags,
    }


def test_analysis_requires_native_choice_and_action_mutation(tmp_path: Path) -> None:
    plan = campaign.build_plan(prefixes=(144,), full_scales=())
    results = tmp_path / "runtime"
    results.mkdir()
    for variant_id, multi, competition, mutation, shift in (
        ("J0_F2_EAGER", 0, 0, 0, 0.0),
        ("J1_F2_JIT_FIFO", 4, 4, 0, 0.0),
        ("J2_F2_JIT_FAIR_AGING_DEADLINE", 4, 4, 2, -1.0),
    ):
        job = campaign.Job.create(variant_id, prefix_segments=144, scale=1)
        path = results / f"{job.job_id}.json"
        path.write_text(
            json.dumps(_result(job, multi=multi, competition=competition, mutation=mutation, shift=shift)),
            encoding="utf-8",
        )

    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    assert analysis["mechanism_decision"] == "JIT_REAL_NATIVE_CHOICE_CONFIRMED"
    by_candidate = {row["candidate"]: row for row in analysis["comparisons"]}
    assert by_candidate["J1_F2_JIT_FIFO"]["real_choice_seam_pass"] is True
    assert by_candidate["J1_F2_JIT_FIFO"]["action_mutation_pass"] is False
    assert by_candidate["J2_F2_JIT_FAIR_AGING_DEADLINE"]["action_mutation_pass"] is True
    assert (
        by_candidate["J2_F2_JIT_FAIR_AGING_DEADLINE"]["performance"][
            "mean_tth_delta_seconds"
        ]
        == -1.0
    )
    assert (tmp_path / "outputs/reports/g4irsf18_jit_mechanism.md").is_file()
    assert (tmp_path / "outputs/reports/g4irsf18_event_amplification.md").is_file()


def test_paired_performance_never_uses_incomplete_bags() -> None:
    baseline = [
        {"task_id": 1, "complete": True, "tth_seconds": 10.0, "source_wait_seconds": 2.0, "network_time_seconds": 8.0},
        {"task_id": 2, "complete": True, "tth_seconds": 20.0, "source_wait_seconds": 4.0, "network_time_seconds": 16.0},
    ]
    candidate = [
        {"task_id": 1, "complete": True, "tth_seconds": 9.0, "source_wait_seconds": 1.0, "network_time_seconds": 8.0},
        {"task_id": 2, "complete": False, "tth_seconds": None, "source_wait_seconds": None, "network_time_seconds": None},
    ]
    result = campaign._paired_performance(baseline, candidate)
    assert result["paired_raw_bag_count"] == 1
    assert result["mean_tth_delta_seconds"] == -1.0
