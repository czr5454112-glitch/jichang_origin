from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.eval import run_g4irsf18_learning_campaign as campaign


def _candidate_row(
    opportunity_id: int,
    candidate_index: int,
    *,
    candidate_count: int = 3,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    event_time = 100.0 + opportunity_id * 7.0
    baseline_request = opportunity_id * 100 + 1
    chosen_request = opportunity_id * 100 + 3
    request_id = opportunity_id * 100 + candidate_index + 1
    row: dict[str, object] = {
        "opportunity_id": opportunity_id,
        "event_time": event_time,
        "destination_node": opportunity_id % 5,
        "controller_generation": opportunity_id,
        "timing_mode": "jit_fair_aging_deadline",
        "candidate_count": candidate_count,
        "baseline_winner_request_id": baseline_request,
        "chosen_winner_request_id": chosen_request,
        "candidate_request_id": request_id,
        "upstream_node": 20 + candidate_index,
        "projected_arrival": event_time - 1.0 - candidate_index * 0.75,
        "deadline_slack": 9.0 + candidate_index * 5.0 - opportunity_id * 0.2,
        "wait_age": 4.0 * opportunity_id + candidate_index * 11.0,
        "destination_service_seconds": 1.5 + candidate_index * 1.3 + (opportunity_id % 3) * 0.2,
        "downstream_queue_pressure": (opportunity_id + candidate_index * 2) % 7,
        "route_score": 0.3 * candidate_index + 0.02 * opportunity_id,
        "static_remaining": 18.0 - candidate_index * 2.0 + opportunity_id * 0.1,
        "task_class_code": 3 + candidate_index,
        "task_class": candidate_index,
        "storage_leg": candidate_index == 2,
        "baseline_winner": candidate_index == 0,
        "chosen_winner": candidate_index == 2,
    }
    if extra:
        row.update(extra)
    return row


def _write_native_trace(
    root: Path,
    *,
    opportunity_count: int = 12,
    add_singleton: bool = True,
    extra: dict[str, object] | None = None,
) -> Path:
    result_dir = root / "outputs/runtime/g4irsf18_jit_campaign"
    result_dir.mkdir(parents=True)
    trace = result_dir / "fixture.opportunities.jsonl.zst"
    rows = [
        _candidate_row(opportunity, candidate, extra=extra)
        for opportunity in range(1, opportunity_count + 1)
        for candidate in range(3)
    ]
    if add_singleton:
        singleton = _candidate_row(99, 0, candidate_count=1)
        singleton["chosen_winner_request_id"] = singleton["candidate_request_id"]
        singleton["chosen_winner"] = True
        rows.append(singleton)
    # The focused unit suite substitutes the JSONL iterator so it can run in
    # the minimal test interpreter, which does not carry the optional zstd
    # wheel.  Production decompression is shared with the established runtime
    # campaigns and still requires zstandard.
    trace.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    companion = trace.with_name("fixture.json")
    companion.write_text(
        json.dumps(
            {
                "schema": "czr005.g4irsf18.jit_campaign_result.v1",
                "status": "COMPLETE",
                "hard_safety": {"pass": True},
                "job": {"job_id": "fixture"},
                "variant": {"timing_mode": "jit_fair_aging_deadline"},
                "counters": {
                    "merge_grant_opportunity_trace_stored_count": len(rows),
                    "merge_grant_opportunity_trace_dropped_count": 0,
                },
                "opportunity_trace_artifact": trace.relative_to(root).as_posix(),
            }
        ),
        encoding="utf-8",
    )
    return trace


def _patch_plain_trace_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def read(path: Path):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)

    monkeypatch.setattr(campaign, "_iter_jsonl_zst", read)


def test_bounded_counterfactual_is_identity_free_and_rewards_old_peer_service() -> None:
    rows = [
        {
            "arrival_lag_seconds": 1.0,
            "arrival_lead_seconds": 0.0,
            "deadline_slack_seconds": 100.0,
            "wait_age_seconds": 1.0,
            "destination_service_seconds": 2.0,
            "downstream_queue_pressure": 0.0,
            "local_route_score": 0.0,
            "static_remaining_seconds": 5.0,
            "task_class_code": 4.0,
            "task_class_priority": 1.0,
            "storage_leg": 0.0,
        },
        {
            "arrival_lag_seconds": 1.0,
            "arrival_lead_seconds": 0.0,
            "deadline_slack_seconds": 2.0,
            "wait_age_seconds": 600.0,
            "destination_service_seconds": 2.0,
            "downstream_queue_pressure": 0.0,
            "local_route_score": 0.0,
            "static_remaining_seconds": 5.0,
            "task_class_code": 4.0,
            "task_class_priority": 1.0,
            "storage_leg": 0.0,
        },
    ]
    young_first = campaign.bounded_local_counterfactual(rows, 0)
    old_first = campaign.bounded_local_counterfactual(rows, 1)
    assert old_first["utility"] > young_first["utility"]
    assert old_first["components"]["estimated_local_event_work_units"] > 0.0


def test_native_no_deadline_sentinel_is_saturated_for_learning() -> None:
    row = _candidate_row(1, 0, extra={"deadline_slack": 1.7976931348623157e308})
    local = campaign._local_row(row, float(row["event_time"]))
    assert local["deadline_slack_seconds"] == 86_400.0
    assert all(np.isfinite(value) for value in local.values())


def test_loader_groups_real_ids_excludes_singletons_and_never_models_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_plain_trace_reader(monkeypatch)
    trace = _write_native_trace(tmp_path)
    limits = campaign.CampaignLimits(
        min_train_opportunities=3,
        min_validation_opportunities=1,
        min_audit_opportunities=1,
        epochs=20,
    )
    opportunities, descriptors, exclusions = campaign.load_native_opportunities(
        [trace], root=tmp_path, limits=limits
    )
    assert len(opportunities) == 12
    assert descriptors[0].row_count == 37
    assert exclusions["singleton"] == 1
    assert len({row.opportunity_id for row in opportunities}) == 12
    assert not any(name.endswith("_id") for name in campaign.MERGE_TRACE_LOCAL_FEATURES)
    assert not any("winner" in name for name in campaign.MERGE_TRACE_LOCAL_FEATURES)
    splits = campaign.split_opportunities(opportunities, limits)
    split_ids = [
        {(row.source_trace, row.opportunity_id) for row in values}
        for values in splits.values()
    ]
    assert split_ids[0].isdisjoint(split_ids[1])
    assert split_ids[0].isdisjoint(split_ids[2])
    assert split_ids[1].isdisjoint(split_ids[2])


def test_loader_rejects_added_outcome_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_plain_trace_reader(monkeypatch)
    trace = _write_native_trace(
        tmp_path,
        opportunity_count=2,
        add_singleton=False,
        extra={"realized_outcome_seconds": 4.2},
    )
    with pytest.raises(
        campaign.G18LearningCampaignError, match="TRACE_CONTAINS_OUTCOME_FIELD"
    ):
        campaign.load_native_opportunities([trace], root=tmp_path)


def test_campaign_trains_four_heads_without_publishing_synthetic_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_plain_trace_reader(monkeypatch)
    trace = _write_native_trace(tmp_path, opportunity_count=15, add_singleton=False)
    limits = campaign.CampaignLimits(
        min_train_opportunities=6,
        min_validation_opportunities=2,
        min_audit_opportunities=2,
        epochs=35,
    )
    result = campaign.run_campaign(
        [trace], root=tmp_path, limits=limits, publish=False
    )
    assert set(result["variants"]) == {
        "J3_LINEAR_RESIDUAL",
        "J4_MLP_RESIDUAL",
        "J5_STANDALONE",
        "J6_SET_SCORER",
        "J7_TEACHER_CF_AFFINE",
    }
    assert result["closed_loop_authorized"] is False
    assert result["counterfactual"]["full_system_clone"] is False
    assert result["selected_variant"] == "J7_TEACHER_CF_AFFINE"
    assert (
        result["variants"]["J7_TEACHER_CF_AFFINE"]["audit"]
        ["teacher_nonhomomorphic_mutation_recall"]
        >= campaign.TEACHER_MUTATION_RECALL_FLOOR
    )
    assert all(
        np.isfinite(metrics["mean_regret"])
        for variant in result["variants"].values()
        for metrics in variant.values()
    )
    historical = {
        row["group"]: row["status"]
        for row in result["ablation_rows"]
        if row["group"] in {"F2_OLD_22", "LEGACY_PLUS_RICH"}
    }
    assert historical == {
        "F2_OLD_22": "NOT_EVALUATED",
        "LEGACY_PLUS_RICH": "NOT_EVALUATED",
    }
    assert not (tmp_path / "artifacts/datasets/g4irsf18_merge_local_counterfactual.jsonl.zst").exists()


def test_no_trace_stops_before_publication(tmp_path: Path) -> None:
    with pytest.raises(campaign.NoRealTraceError, match="NO_REAL_NATIVE_JIT_TRACE"):
        campaign.run_campaign([], root=tmp_path)
    assert not (tmp_path / "outputs/reports/g4irsf18_learning_campaign.md").exists()


def test_default_discovery_selects_only_j2_teacher_traces(tmp_path: Path) -> None:
    names = (
        "j0_f2_eager__s512.opportunities.jsonl.zst",
        "j1_f2_jit_fifo__s512.opportunities.jsonl.zst",
        "j2_f2_jit_fair_aging_deadline__s512.opportunities.jsonl.zst",
    )
    for name in names:
        (tmp_path / name).write_bytes(b"")
    discovered = campaign.discover_traces(tmp_path, ())
    assert [path.name for path in discovered] == [names[2]]


def test_complete_contract_publishes_models_policy_manifest_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_plain_trace_reader(monkeypatch)
    monkeypatch.setattr(
        campaign,
        "_jsonl_zst_bytes",
        lambda rows: ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode(),
    )
    trace = _write_native_trace(tmp_path, opportunity_count=10, add_singleton=False)
    result = campaign.run_campaign(
        [trace],
        root=tmp_path,
        limits=campaign.CampaignLimits(
            min_train_opportunities=6,
            min_validation_opportunities=2,
            min_audit_opportunities=2,
            epochs=20,
        ),
    )
    assert len(result["artifacts"]) == 14
    assert (tmp_path / "artifacts/models/g4irsf18_j3_linear_residual.json").is_file()
    assert (tmp_path / "artifacts/models/g4irsf18_j6_set_scorer.json").is_file()
    teacher_model = json.loads(
        (tmp_path / "artifacts/models/g4irsf18_j7_teacher_cf_affine.json").read_text()
    )
    assert teacher_model["schema"] == "czr005.g4irsf18.teacher_counterfactual_linear_merge.v1"
    assert teacher_model["family"] == "teacher_warm_start_counterfactual_advantage_affine"
    assert teacher_model["feature_contract"] == "MERGE_TRACE_LOCAL_V1"
    assert teacher_model["score_direction"] == "higher_is_better"
    assert teacher_model["nonfinite_policy"] == "OOD_AND_J2_FALLBACK"
    assert teacher_model["out_of_range_policy"].startswith("OOD_AND_J2_FALLBACK")
    assert "OOD_AND_J2_FALLBACK" in teacher_model["candidate_count_policy"]
    assert teacher_model["tie_break"] == "fifo"
    assert teacher_model["tie_break_scope"] == "finite_in_contract_equal_score_only"
    assert (
        tmp_path / "outputs/tables/g4irsf18_teacher_cf_blend_sweep.csv"
    ).is_file()
    policy = json.loads(
        (tmp_path / "artifacts/policies/g4irsf18_learning_research_policy.json").read_text()
    )
    assert policy["authorization"] == "RESEARCH_FIXED_WORKLOAD_CANDIDATE_NATIVE_PARITY_REQUIRED"
    assert policy["normal_flow_closed_loop_authorized"] is False
    ablation = (tmp_path / "outputs/reports/g4irsf18_feature_ablation.md").read_text()
    assert "F2_OLD_22" in ablation
    assert "LEGACY_PLUS_RICH" in ablation
    assert "NOT_EVALUATED" in ablation
