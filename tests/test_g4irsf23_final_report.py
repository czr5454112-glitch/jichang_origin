from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.eval import g4irsf23_final_report as final


FORMAL_FIXTURE = Path(
    "tests/fixtures/g4irsf23_precursor_route_formal_delivery_no_go.json"
)
EXTERNALITY_FIXTURE = Path(
    "tests/fixtures/g4irsf23_externality_neighborhood_no_go.json"
)


def _read(relative: Path) -> dict:
    return json.loads((final.ROOT / relative).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baselines() -> dict:
    return _read(final.DEFAULT_BASELINE)


@pytest.fixture(scope="module")
def source() -> dict:
    return _read(final.DEFAULT_SOURCE)


@pytest.fixture(scope="module")
def precursor() -> dict:
    return _read(final.DEFAULT_PRECURSOR)


@pytest.fixture(scope="module")
def precursor_formal_no_go() -> dict:
    return _read(FORMAL_FIXTURE)


def test_required_two_baselines_are_split_across_three_denominators(
    baselines: dict, source: dict, precursor: dict
) -> None:
    summary = final.build_decision_summary(baselines, source, precursor)
    required = summary["required_baselines"]
    f2 = required["frozen_f2"]["one_x"]
    assert (
        f2["raw_bag_count"],
        f2["processed_segment_count"],
        f2["complete_raw_bags"],
        f2["failed_segments"],
        f2["conflicts"],
        f2["runtime_full_astar_calls"],
    ) == (28_506, 43_603, 28_506, 0, 0, 0)
    assert f2["original_entry_mean_minutes"] == pytest.approx(41.514218717973414)
    assert f2["original_entry_p95_seconds"] == pytest.approx(7349.348647499981)
    assert f2["original_entry_p99_seconds"] == pytest.approx(10789.015762999989)
    hca_baseline = required["original_hca_star"]
    hca = hca_baseline["one_x"]
    assert (
        hca_baseline["evidence_status"]
        == "HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT"
    )
    assert hca_baseline["fresh_java_rerun"] is False
    assert hca["speed_mps"] == 2.5
    assert hca["java_release_time_tth_min_minutes"] == pytest.approx(3.13333333)
    assert hca["java_release_time_tth_mean_minutes"] == pytest.approx(5.19722515)
    assert hca["java_release_time_tth_max_minutes"] == pytest.approx(24.31666667)
    assert hca["legacy_mislabeled_original_entry_min_minutes"] == pytest.approx(
        3.11684817
    )
    assert hca["legacy_mislabeled_original_entry_mean_minutes"] == pytest.approx(
        5.76493675
    )
    assert hca["legacy_mislabeled_original_entry_max_minutes"] == pytest.approx(
        27.14962583
    )
    assert hca["matched_raw_entry_time_tth_mean_minutes"] == pytest.approx(
        43.13593828041816
    )
    panel = summary["denominator_panel"]
    assert panel["baseline_ids"] == [
        "G4IRSF13_F2_FROZEN",
        "original_project_iot_drpa_hca_star",
    ]
    rows = {row["denominator"]: row for row in panel["rows"]}
    assert set(rows) == {
        "processed_segment_attempt_time_tth",
        "java_release_time_tth",
        "original_entry_time_tth",
    }
    assert rows["processed_segment_attempt_time_tth"]["frozen_f2"][
        "status"
    ] == "NOT_REPORTED_FOR_F2"
    assert rows["processed_segment_attempt_time_tth"]["original_hca_star"][
        "mean_minutes"
    ] == pytest.approx(3.96712271)
    assert rows["java_release_time_tth"]["original_hca_star"][
        "mean_minutes"
    ] == pytest.approx(5.19722515)
    original_entry = rows["original_entry_time_tth"]
    assert original_entry["frozen_f2"]["mean_minutes"] == pytest.approx(
        41.514218717973414
    )
    assert original_entry["original_hca_star"]["mean_minutes"] == pytest.approx(
        43.13593828041816
    )
    assert original_entry["fresh_matched_winner_claim_allowed"] is False
    assert (
        panel["unmapped_diagnostics"]["status"]
        == "DO_NOT_SUBSTITUTE_IN_THE_THREE_DENOMINATOR_PANEL"
    )

    report = final.render_markdown(summary)
    assert "Raw bags / processed segments | 28506 / 43603" in report
    assert "Completed segments | 43603" in report
    assert (
        "Complete raw bags / failed segments / conflicts / runtime full A* calls | "
        "28506 / 0 / 0 / 0" in report
    )
    assert "N/A / 41.514218718 / N/A" in report
    assert "7349.348647500 / 10789.015763000" in report
    assert "Pass-time-anchored mean diagnostic (min) | 4.143217184" in report
    assert "`HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT`" in report
    assert "fresh Java rerun: `False`; scope: `1x / 2.5 m/s`" in report
    assert "3.133333330 | 3.967122710 | 5.983333330" in report
    assert "3.133333330 | 5.197225150 | 24.316666670" in report
    assert "3.116848170 | 5.764936750 | 27.149625830" in report
    assert "N/A | 43.135938280 | N/A" in report
    assert "2x `N/A_NOT_IN_PAPER_PROTOCOL`" in report
    assert "4x `N/A_NOT_IN_PAPER_PROTOCOL`" in report
    assert "legacy mislabeled 字段仅作诊断，不填补比较面板" in report


def test_all_paper_tables_are_explicit_and_paper_reported_only(
    baselines: dict,
) -> None:
    summary = final.build_decision_summary(baselines)
    panels = summary["paper"]["panels"]
    assert len(panels["table_5_2_speed_sweep"]["rows"]) == 4
    assert (
        panels["table_5_2_speed_sweep"]["evidence_status"]
        == "PAPER_REPORTED_ONLY"
    )
    assert len(panels["table_5_3_iot_drpa_vs_dispersed_heuristic"]["rows"]) == 3
    assert len(panels["table_5_4_dynamic_iot_drpa_vs_static_lra_star"]["rows"]) == 12
    assert len(panels["table_5_5_faults"]["rows"]) == 16
    assert panels["table_5_5_faults"]["evidence_status"] == "PAPER_REPORTED_ONLY"


def test_current_missing_formal_and_externality_stay_pending(
    baselines: dict, source: dict, precursor: dict
) -> None:
    summary = final.build_decision_summary(baselines, source, precursor)
    stages = summary["stages"]
    assert summary["status"] == "PENDING"
    assert stages["23C_source_pilot"]["decision_status"] == "TARGETED_SOURCE_NO_SUPPORT"
    assert stages["23D_source_formal"] == {
        "evidence_status": "NOT_TRIGGERED",
        "decision_status": "NOT_TRIGGERED_BY_SOURCE_PILOT_CONTINUATION_GATE",
        "reason": "SOURCE_PILOT_CONTINUATION_GATE_NOT_MET",
    }
    for stage_id in (
        "23E_feature_reduction",
        "23G_offline_gate",
        "23H_native_closed_loop",
    ):
        assert stages[stage_id]["evidence_status"] == "NOT_TRIGGERED"
        assert (
            stages[stage_id]["decision_status"]
            == "NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE"
        )
    route = stages["23I_precursor_route"]
    assert route["pilot_decision_status"] == "NO_GO_PRECURSOR_PILOT_SUPPORT"
    assert route["formal_evidence_status"] == "NOT_RUN"
    assert route["formal_decision_status"] == "PENDING"
    assert route["formal_exact_pair_gate_pass"] is False
    assert route["evidence_status"] == "PENDING"
    assert route["decision_status"] == "PENDING_PRECURSOR_FORMAL_GATE"
    assert stages["23J_externality_neighborhood"] == {
        "evidence_status": "PENDING",
        "decision_status": "PENDING_PRECURSOR_FORMAL_GATE",
        "reason": "PRECURSOR_FORMAL_DECISION_NOT_COMPLETE",
    }
    assert summary["final_decision"]["candidate_promotion_authorized"] is False
    assert summary["final_decision"]["closed_loop_performance_claim"] == "NOT_RUN"


def test_externality_plan_cannot_be_misreported_as_causal_result(
    baselines: dict,
) -> None:
    with pytest.raises(final.FinalReportError, match="compact result or summary"):
        final.build_decision_summary(
            baselines,
            externality={
                "schema": "czr005.g4irsf23.externality_neighborhood_plan.v1",
                "status": "COMPLETE",
            },
        )


def _externality_no_go() -> dict:
    return _read(EXTERNALITY_FIXTURE)


def test_pilot_and_externality_no_go_do_not_replace_precursor_formal(
    baselines: dict, source: dict, precursor: dict
) -> None:
    summary = final.build_decision_summary(
        baselines, source, precursor, _externality_no_go()
    )
    decision = summary["final_decision"]
    assert decision["status"] == "PENDING"
    assert decision["label"] == "PENDING"
    assert decision["candidate_promotion_authorized"] is False
    assert decision["closed_loop_performance_claim"] == "NOT_RUN"


def test_externality_fixture_matches_fairness_aware_producer_shape(
    baselines: dict,
) -> None:
    externality = _externality_no_go()
    assert "individual_fairness_claimed" not in externality
    assert externality["individual_fairness_evaluated"] is True
    assert set(externality["gates"]) == {
        "execution_coverage",
        "recognized_execution_outcomes",
        "action_changing_rate",
        "fair_system_beneficial_count",
        "fair_system_beneficial_block_pressure_cell_count",
        "heldout_local_signature",
    }
    summary = final.build_decision_summary(baselines, externality=externality)
    stage = summary["stages"]["23J_externality_neighborhood"]
    assert stage["evidence_status"] == "COMPLETE"
    assert stage["attempted_group_count"] == 256
    assert stage["execution_coverage_count"] == 256
    assert stage["action_applied_count"] == 254
    assert stage["guard_abstain_count"] == 2
    assert stage["action_changing_rate"] == 254 / 256
    assert stage["guard_abstain_reasons"] == {
        "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED": 2
    }
    assert stage["effect_complete_count"] == 254
    assert stage["fair_system_beneficial_count"] == 1
    assert stage["fair_system_beneficial_cell_count"] == 1
    assert stage["system_beneficial_but_costly_count"] == 2
    assert stage["system_beneficial_but_unfair_count"] == 2
    assert stage["individual_fairness_evaluated"] is True
    assert stage["continuation_cell_coverage_uses_fair_system_beneficial"] is True
    assert stage["selection_scope"] == "ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY"
    assert stage["one_hop_pressure_bins"] == ["q16_23", "q24_31", "q32_plus"]
    assert stage["two_hop_queue_pressure_used"] is False
    assert stage["heldout_local_signature_feature"] == "one_hop_target_queue_bin"
    assert stage["system_tail_hard_gate_metrics"] == [
        "raw_bag_p95_delta_seconds",
        "raw_bag_p99_delta_seconds",
    ]
    assert stage["raw_bag_max_delta_is_diagnostic_only"] is True
    assert stage["raw_bag_max_delta_seconds_diagnostic"]["count"] == 254
    assert stage["raw_bag_max_delta_seconds_diagnostic"]["max"] == 12.0
    assert stage["heldout_local_signature_scope"] == "SYSTEM_BENEFICIAL_ONLY"
    assert stage["heldout_local_signature_individual_fairness_used"] is False
    assert stage["individual_fairness_contract"] == (
        "FROZEN_PRE_ACTION_DEADLINE_HEADROOM_AND_TREATMENT_CURRENT_BAG_OUTCOME"
    )

    report = final.render_markdown(summary)
    assert "Held-out local signature scope: `SYSTEM_BENEFICIAL_ONLY`" in report
    assert "Selection scope: `ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY`" in report
    assert "two-hop pressure used: `False`" in report
    assert "System tail hard gate: `p95/p99 <= +0.001 s`" in report
    assert "raw-bag max delta diagnostic only (not a hard gate)" in report
    assert "individual fairness used by held-out signature: `False`" in report
    assert "Fair cell coverage remains a separate continuation gate" in report


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["gates"].update(
                {"system_beneficial_count": False}
            ),
            "separate execution, applicability, and effect booleans",
        ),
        (
            lambda payload: payload.update(
                {"individual_fairness_evaluated": False}
            ),
            "frozen individual-fairness contract",
        ),
        (
            lambda payload: payload.update(
                {"system_beneficial_but_unfair_count": 1}
            ),
            "producer partition contract",
        ),
        (
            lambda payload: payload["gates"].update(
                {"fair_system_beneficial_count": True}
            ),
            "disagree with its gates",
        ),
        (
            lambda payload: payload.update(
                {"status": "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT"}
            ),
            "decision label disagrees",
        ),
        (
            lambda payload: payload.update(
                {"two_hop_queue_pressure_used": True}
            ),
            "one-hop selection contract",
        ),
        (
            lambda payload: payload["thresholds"].update(
                {"system_p95_p99_delta_seconds_max": 0.002}
            ),
            "thresholds or held-out signature",
        ),
        (
            lambda payload: payload.update(
                {"raw_bag_max_delta_is_diagnostic_only": False}
            ),
            "p95/p99-only tail hard-gate contract",
        ),
    ],
)
def test_externality_fairness_handoff_fails_closed_on_schema_drift(
    baselines: dict,
    mutation: object,
    message: str,
) -> None:
    invalid = _externality_no_go()
    mutation(invalid)
    with pytest.raises(final.FinalReportError, match=message):
        final.build_decision_summary(baselines, externality=invalid)


def test_externality_fairness_aware_pass_label_is_accepted_only_when_all_gates_pass(
    baselines: dict,
) -> None:
    externality = _externality_no_go()
    externality.update(
        {
            "status": "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT",
            "system_beneficial_count": 20,
            "system_beneficial_cell_count": 3,
            "fair_system_beneficial_count": 20,
            "fair_system_beneficial_cell_count": 3,
            "system_beneficial_but_unfair_count": 0,
            "continuation_pass": True,
        }
    )
    externality["gates"] = {key: True for key in externality["gates"]}
    externality["heldout_local_signature"]["pass"] = True
    summary = final.build_decision_summary(baselines, externality=externality)
    stage = summary["stages"]["23J_externality_neighborhood"]
    assert stage["decision_status"] == "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
    assert stage["continuation_pass"] is True
    assert summary["status"] == "PENDING"


def test_exact_formal_2048_and_exact_externality_no_go_close_only_tested_seams(
    baselines: dict,
    source: dict,
    precursor: dict,
    precursor_formal_no_go: dict,
) -> None:
    summary = final.build_decision_summary(
        baselines,
        source,
        precursor,
        _externality_no_go(),
        precursor_formal_no_go,
    )
    route = summary["stages"]["23I_precursor_route"]
    assert route["formal_decision_status"] == final.PRECURSOR_FORMAL_NO_GO
    assert route["formal_h_bag_complete_group_count"] == 2048
    assert route["formal_h_system_sparse_reused_group_count"] == 256
    assert route["formal_h_bag_only_group_count"] == 1792
    assert route["formal_new_h_system_group_count"] == 0
    assert route["formal_new_h_system_target_count"] == 0
    assert (
        route["formal_h_system_evidence_scope"]
        == "SPARSE_256_REUSED_NOT_2048_SYSTEM_LABELS"
    )
    decision = summary["final_decision"]
    assert decision["status"] == "COMPLETE_LOCAL_ACTION_SUPPORT_NO_GO"
    assert decision["label"] == "TESTED_SEAM_LOCAL_ACTION_CEILING"
    assert "limited to the tested" in decision["reason"]
    assert decision["candidate_promotion_authorized"] is False
    assert decision["closed_loop_performance_claim"] == "NOT_RUN"
    assert (
        summary["denominator_panel"]["candidate_metrics_status"]
        == "NOT_RUN_AFTER_SUPPORT_NO_GO"
    )


def test_formal_pilot_style_pass_is_normalized_without_inflating_hsystem(
    baselines: dict,
    source: dict,
    precursor: dict,
    precursor_formal_no_go: dict,
) -> None:
    formal_pass = deepcopy(precursor_formal_no_go)
    compact = formal_pass["precursor_formal"]
    compact["status"] = "PASS_PRECURSOR_PILOT_SUPPORT"
    compact["pilot_support_pass"] = True
    compact["fair_promotion_group_count"] = 16
    compact["block8_fair_promotion_group_count"] = 4
    compact["fair_promotion_strata_count"] = 3
    compact["gates"] = {key: True for key in compact["gates"]}
    formal_pass["formal_decision_status"] = final.PRECURSOR_FORMAL_PASS
    formal_pass["formal_support_pass"] = True
    formal_pass["formal_counts"].update(
        {
            "fair_promotion_group_count": 16,
            "block8_fair_promotion_group_count": 4,
        }
    )
    formal_pass["tiny_mlp_unlock"]["observed_formal_fair_positive_count"] = 16
    summary = final.build_decision_summary(
        baselines, source, precursor, None, formal_pass
    )
    route = summary["stages"]["23I_precursor_route"]
    assert route["formal_evidence_status"] == "COMPLETE"
    assert route["formal_decision_status"] == final.PRECURSOR_FORMAL_PASS
    assert route["formal_h_system_sparse_reused_group_count"] == 256
    assert route["formal_h_bag_only_group_count"] == 1792
    assert summary["status"] == "PENDING"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["exact_pair_gate"].update(
                {"observed_target_count": 4095}
            ),
            "exact pair gate is incomplete",
        ),
        (
            lambda payload: payload["precursor_formal"].update(
                {"h_system_complete_group_count": 2048}
            ),
            "H_bag=2048/H_system=256",
        ),
        (
            lambda payload: payload["identity_audit"].update(
                {"new_h_system_target_count": 1792}
            ),
            "identity audit must prove",
        ),
        (
            lambda payload: payload["precursor_formal"]["gates"].update(
                {"fair_promotion_group_count": True}
            ),
            "counts disagree with its gates",
        ),
    ],
)
def test_formal_handoff_fails_closed_on_scope_or_exact_drift(
    baselines: dict,
    precursor_formal_no_go: dict,
    mutation: object,
    message: str,
) -> None:
    invalid = deepcopy(precursor_formal_no_go)
    mutation(invalid)
    with pytest.raises(final.FinalReportError, match=message):
        final.build_decision_summary(
            baselines, precursor_formal=invalid
        )


def test_formal_fixture_matches_actual_producer_identity_audit_shape(
    baselines: dict,
    precursor_formal_no_go: dict,
) -> None:
    assert "evidence_counts" not in precursor_formal_no_go
    identity = precursor_formal_no_go["identity_audit"]
    assert (
        precursor_formal_no_go["formal_decision_status"]
        == final.PRECURSOR_FORMAL_NO_GO
    )
    assert precursor_formal_no_go["formal_support_pass"] is False
    assert precursor_formal_no_go["formal_counts"] == {
        "h_bag_complete_group_count": 2048,
        "h_system_sparse_reused_group_count": 256,
        "h_bag_only_group_count": 1792,
        "new_h_system_group_count": 0,
        "new_h_system_target_count": 0,
        "fair_promotion_group_count": 6,
        "block8_fair_promotion_group_count": 0,
        "required_fair_promotion_group_count": 16,
        "required_block8_fair_promotion_group_count": 4,
    }
    assert identity["pilot_h_system_group_count"] == 256
    assert identity["pilot_h_bag_only_group_count"] == 256
    assert identity["delta_h_bag_only_group_count"] == 1536
    assert identity["new_h_system_target_count"] == 0
    assert identity["full_formal_execution_target_count"] == 4096
    assert identity["exact_execution_partition"] is True
    summary = final.build_decision_summary(
        baselines, precursor_formal=precursor_formal_no_go
    )
    route = summary["stages"]["23I_precursor_route"]
    assert route["formal_evidence_status"] == "COMPLETE"
    assert route["formal_h_bag_only_group_count"] == 256 + 1536
    assert route["formal_fair_promotion_group_count"] == 6
    assert route["formal_block8_fair_promotion_group_count"] == 0
    assert route["formal_required_fair_promotion_group_count"] == 16
    assert route["formal_required_block8_fair_promotion_group_count"] == 4
    assert route["tiny_mlp_unlock"] == {
        "required_formal_fair_positive_count": 40,
        "required_heldout_fair_positive_count": 12,
        "observed_formal_fair_positive_count": 6,
        "observed_heldout_fair_positive_count": 0,
        "heldout_evidence_status": "NOT_RUN",
        "nonlinear_regret_requirement": "STABLE_NONLINEAR_REGRET_REQUIRED",
        "nonlinear_regret_evidence_status": "NOT_RUN",
        "unlocked": False,
    }


def test_cli_stages_and_replaces_both_outputs_without_simulation(
    tmp_path: Path,
) -> None:
    json_output = tmp_path / "decision.json"
    report_output = tmp_path / "decision.md"
    assert final.main(
        [
            "--root",
            str(final.ROOT),
            "--precursor-formal-summary",
            str(tmp_path / "formal_not_run.json"),
            "--externality-summary",
            str(tmp_path / "not_run.json"),
            "--json-output",
            str(json_output),
            "--report-output",
            str(report_output),
        ]
    ) == 0
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    report = report_output.read_text(encoding="utf-8")
    assert payload["schema"] == final.FINAL_SCHEMA
    assert payload["status"] == "PENDING"
    assert "Table 5.2" in report
    assert "Table 5.3" in report
    assert "Table 5.4" in report
    assert "Table 5.5" in report
    assert (
        "`23J_externality_neighborhood` | `PENDING` | "
        "`PENDING_PRECURSOR_FORMAL_GATE`" in report
    )
    assert (
        "Externality fairness handoff: `PENDING` / "
        "`PENDING_PRECURSOR_FORMAL_GATE`" in report
    )
    assert not list(tmp_path.glob("*.tmp"))


def test_cli_accepts_the_optional_formal_handoff(
    tmp_path: Path,
) -> None:
    json_output = tmp_path / "formal-decision.json"
    report_output = tmp_path / "formal-decision.md"
    assert final.main(
        [
            "--root",
            str(final.ROOT),
            "--precursor-formal-summary",
            str(final.ROOT / FORMAL_FIXTURE),
            "--externality-summary",
            str(tmp_path / "not_run.json"),
            "--json-output",
            str(json_output),
            "--report-output",
            str(report_output),
        ]
    ) == 0
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    route = payload["stages"]["23I_precursor_route"]
    assert payload["status"] == "PENDING"
    assert route["formal_decision_status"] == final.PRECURSOR_FORMAL_NO_GO
    assert route["formal_h_system_sparse_reused_group_count"] == 256
    report = report_output.read_text(encoding="utf-8")
    assert "This is never described as 2,048 system labels" in report


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(
            {"formal_decision_status": final.PRECURSOR_FORMAL_PASS}
        ),
        lambda payload: payload.update({"formal_support_pass": True}),
        lambda payload: payload["formal_counts"].update(
            {"h_system_sparse_reused_group_count": 2048}
        ),
        lambda payload: payload["formal_counts"].update(
            {"required_fair_promotion_group_count": 40}
        ),
    ],
)
def test_formal_top_level_status_support_and_counts_fail_closed(
    baselines: dict,
    precursor_formal_no_go: dict,
    mutation: object,
) -> None:
    invalid = deepcopy(precursor_formal_no_go)
    mutation(invalid)
    with pytest.raises(final.FinalReportError, match="top-level status/support/counts"):
        final.build_decision_summary(baselines, precursor_formal=invalid)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("required_fair_promotion_groups", 40),
        ("required_block8_fair_promotion_groups", 12),
    ],
)
def test_formal_promotion_thresholds_fail_closed_above_16_and_4(
    baselines: dict,
    precursor_formal_no_go: dict,
    field: str,
    value: int,
) -> None:
    invalid = deepcopy(precursor_formal_no_go)
    invalid["precursor_formal"]["thresholds"][field] = value
    with pytest.raises(final.FinalReportError, match="16 total / 4 block-8"):
        final.build_decision_summary(baselines, precursor_formal=invalid)


def test_tiny_mlp_unlock_keeps_40_12_and_nonlinear_regret_separate(
    baselines: dict,
    precursor_formal_no_go: dict,
) -> None:
    summary = final.build_decision_summary(
        baselines, precursor_formal=precursor_formal_no_go
    )
    unlock = summary["stages"]["23I_precursor_route"]["tiny_mlp_unlock"]
    assert unlock["observed_formal_fair_positive_count"] == 6
    assert unlock["required_formal_fair_positive_count"] == 40
    assert unlock["observed_heldout_fair_positive_count"] == 0
    assert unlock["required_heldout_fair_positive_count"] == 12
    assert unlock["nonlinear_regret_evidence_status"] == "NOT_RUN"
    assert unlock["unlocked"] is False

    invalid = deepcopy(precursor_formal_no_go)
    invalid["tiny_mlp_unlock"]["required_formal_fair_positive_count"] = 16
    with pytest.raises(final.FinalReportError, match="tiny-MLP unlock"):
        final.build_decision_summary(baselines, precursor_formal=invalid)


def test_required_30_questions_track_completed_not_triggered_and_pending_gates(
    baselines: dict,
    source: dict,
    precursor: dict,
) -> None:
    summary = final.build_decision_summary(baselines, source, precursor)
    audit = summary["required_question_audit"]
    assert audit["schema"] == "czr005.g4irsf23.required_30_questions.v1"
    assert audit["question_count"] == 30
    rows = {row["number"]: row for row in audit["rows"]}
    assert sorted(rows) == list(range(1, 31))
    assert rows[2]["status"] == "COMPLETE"
    assert "不换 bag" in rows[2]["answer"]
    assert rows[8]["status"] == "COMPLETE"
    assert "promotion-eligible usable/strong fair positives = 0" in rows[8][
        "answer"
    ]
    for number in (11, 13, 14, 15, 16):
        assert (
            rows[number]["status"]
            == "NOT_TRIGGERED_BY_SOURCE_CAUSAL_SUPPORT_GATE"
        )
    assert rows[23]["status"] == "PENDING"
    assert "Formal 2,048" in rows[23]["answer"]
    for number in (18, 19, 21, 22, 26, 27, 28, 29):
        assert rows[number]["status"] == "PENDING"
    assert rows[30]["status"] == "COMPLETE"
    assert "precursor Formal 2,048" in rows[30]["answer"]


def test_continuous_source_and_precursor_effect_cost_distributions_are_exposed(
    baselines: dict,
    source: dict,
    precursor: dict,
) -> None:
    summary = final.build_decision_summary(baselines, source, precursor)
    source_stage = summary["stages"]["23C_source_pilot"]
    components = source_stage["component_mean_delta_seconds_per_raw_bag"]
    assert components["delta_direction"] == "treatment_minus_baseline"
    assert components["unit"] == "seconds_per_complete_raw_bag"
    assert components["all"]["pair_count"] == 176
    assert components["all"]["metrics"][
        "raw_bag_network_time_mean_delta_seconds"
    ]["mean"] == pytest.approx(-8.124665138997678e-05)

    route = summary["stages"]["23I_precursor_route"]
    effects = route["pilot_h_system_effect_distribution"]
    assert effects["panel"]["action_count"] == 512
    assert effects["panel"]["group_count"] == 256
    assert effects["fair_promotions"]["action_count"] == 6
    assert effects["fair_promotions"]["group_count"] == 6
    assert effects["panel"]["metrics"]["raw_bag_mean_delta_seconds"][
        "mean"
    ] == pytest.approx(0.9798772883792615)
    assert effects["fair_promotions"]["metrics"][
        "raw_bag_mean_delta_seconds"
    ]["mean"] == pytest.approx(-3.6096462148421438)
    assert effects["fair_promotions"]["metrics"][
        "current_bag_cost_seconds"
    ]["max"] == pytest.approx(1495.4)

    questions = {
        row["number"]: row for row in summary["required_question_audit"]["rows"]
    }
    assert "fair promotions=6/6" in questions[23]["answer"]
    assert "cost mean/max +753.050/+1495.400s" in questions[23]["answer"]
    report = final.render_markdown(summary)
    assert "## Source component decomposition" in report
    assert "## Precursor Pilot H_system effect/cost distribution" in report
    assert "完整 panel 为 512 actions / 256 groups" in report
    assert "fair promotions 为 6 actions / 6 groups" in report
    assert "| Mean TTH delta | -8.530958395 | +0.979877288" in report


@pytest.mark.parametrize(
    ("payload_name", "mutation", "message"),
    [
        (
            "source",
            lambda payload: payload["h_system_effect"][
                "component_mean_delta_seconds_per_raw_bag"
            ].update({"h_system_pair_count": 175}),
            "count/unit/direction contract",
        ),
        (
            "precursor",
            lambda payload: payload["precursor_pilot"][
                "h_system_effect_distribution"
            ]["panel"].update({"action_count": 511}),
            "count/direction contract",
        ),
        (
            "precursor",
            lambda payload: payload["precursor_pilot"][
                "h_system_effect_distribution"
            ]["fair_promotions"]["metrics"]["current_bag_cost_seconds"].update(
                {"missing_count": 1}
            ),
            "contains missing values",
        ),
    ],
)
def test_continuous_effect_handoff_rejects_material_shape_drift(
    baselines: dict,
    source: dict,
    precursor: dict,
    payload_name: str,
    mutation: object,
    message: str,
) -> None:
    invalid_source = deepcopy(source)
    invalid_precursor = deepcopy(precursor)
    target = invalid_source if payload_name == "source" else invalid_precursor
    mutation(target)
    with pytest.raises(final.FinalReportError, match=message):
        final.build_decision_summary(
            baselines,
            invalid_source,
            invalid_precursor,
        )


def test_formal_no_go_triggers_externality_pending_without_using_pilot_as_overall(
    baselines: dict,
    source: dict,
    precursor: dict,
    precursor_formal_no_go: dict,
) -> None:
    summary = final.build_decision_summary(
        baselines,
        source,
        precursor,
        None,
        precursor_formal_no_go,
    )
    route = summary["stages"]["23I_precursor_route"]
    assert route["pilot_decision_status"] == "NO_GO_PRECURSOR_PILOT_SUPPORT"
    assert route["decision_status"] == final.PRECURSOR_FORMAL_NO_GO
    assert route["evidence_status"] == "COMPLETE"
    externality = summary["stages"]["23J_externality_neighborhood"]
    assert externality == {
        "evidence_status": "PENDING",
        "decision_status": "PENDING_EXTERNALITY_NEIGHBORHOOD_EVIDENCE",
        "reason": "TRIGGERED_BY_PRECURSOR_FORMAL_NO_GO_GATE",
    }
    report = final.render_markdown(summary)
    assert "## 23I Precursor 分层证据" in report
    assert (
        "`23I_precursor_route` | `COMPLETE` | "
        "`NO_GO_PRECURSOR_FORMAL_SUPPORT`" in report
    )
    assert "| Pilot | `COMPLETE` | `NO_GO_PRECURSOR_PILOT_SUPPORT`" in report
    assert "| Formal | `COMPLETE` | `NO_GO_PRECURSOR_FORMAL_SUPPORT`" in report


def test_all_local_no_go_marks_scale_fault_questions_not_triggered(
    baselines: dict,
    source: dict,
    precursor: dict,
    precursor_formal_no_go: dict,
) -> None:
    summary = final.build_decision_summary(
        baselines,
        source,
        precursor,
        _externality_no_go(),
        precursor_formal_no_go,
    )
    assert summary["stages"]["23K_scale_and_fault"] == {
        "evidence_status": "NOT_TRIGGERED",
        "decision_status": "NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE",
        "reason": "NO_CAUSALLY_SUPPORTED_G23_CANDIDATE_EXISTS",
    }
    rows = {
        row["number"]: row for row in summary["required_question_audit"]["rows"]
    }
    assert rows[23]["status"] == "COMPLETE"
    assert rows[25]["status"] == "COMPLETE"
    for number in (18, 19, 21, 22, 26, 27, 28, 29):
        assert (
            rows[number]["status"]
            == "NOT_TRIGGERED_BY_CANDIDATE_PROMOTION_GATE"
        )
    assert "更早一个真实 merge-token 接口" in rows[30]["answer"]
    report = final.render_markdown(summary)
    assert "## 规范 30 问" in report
    assert "| 30 | 下一阶段最窄、最有价值的问题是什么？ | `COMPLETE` |" in report
