from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval import report_g4irsf17_evidence as report
from scripts.eval import run_g4irsf17_system_campaign as system_campaign


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_canonical_reports_do_not_collide_with_system_track_reports() -> None:
    canonical = {
        report.G2_REPORT,
        report.FAULT_REPORT,
        report.SCALE_REPORT,
        report.FINAL_REPORT,
    }
    system_track = {
        system_campaign.G2_REPORT,
        system_campaign.FAULT_REPORT,
        system_campaign.SCALE_REPORT,
        system_campaign.FINAL_REPORT,
    }
    assert canonical.isdisjoint(system_track)
    assert all(path.stem.endswith("system_track") for path in system_track)


def _complete_manifest() -> dict[str, object]:
    return {
        "stages": {
            "source_wait_diagnosis": {
                "status": "COMPLETE",
                "summary": {
                    "downstream_backpressure_share": 0.80,
                    "matched_bag_count": 100,
                    "positive_additional_source_wait_seconds": 15.0,
                    "source_wait_delta_mean_seconds_per_raw_bag": 0.15,
                    "network_time_delta_mean_seconds_per_raw_bag": -0.06,
                    "tth_delta_mean_seconds_per_raw_bag": 0.09,
                },
            },
            "closed_loop_ladder": {"status": "COMPLETE", "decision": "COMPLETE"},
            "native_fault_campaign": {"status": "COMPLETE", "decision": "COMPLETE"},
            "scale_benchmark": {"status": "COMPLETE", "decision": "COMPLETE"},
        }
    }


def _populate_full_evidence(root: Path) -> None:
    _write_json(root / report.MANIFEST, _complete_manifest())
    _write_json(
        root / report.SYSTEM_PLAN,
        {"g2_decision": {"triggered": True, "causal_gate_pass": False, "decision": "G2_PIVOT_TRIGGERED_PILOT_REQUIRED"}},
    )
    _write_csv(
        root / report.WAIT_TOPOLOGY,
        [
            {
                "aggregation": "CAUSE",
                "reason": "DESTINATION_MERGE_TOKEN",
                "cause_class": "DOWNSTREAM_BACKPRESSURE",
                "h5_native_wait_seconds": 120.0,
                "off_native_wait_seconds": 100.0,
                "attributed_positive_additional_wait_seconds": 20.0,
                "source_node": "",
                "blocker_node": "",
                "time_bucket": "",
                "leg_type": "",
            },
            {
                "aggregation": "SOURCE_BLOCKER_TIME_LEG",
                "reason": "DESTINATION_MERGE_TOKEN",
                "cause_class": "",
                "h5_native_wait_seconds": 120.0,
                "off_native_wait_seconds": 100.0,
                "attributed_positive_additional_wait_seconds": 20.0,
                "source_node": "52",
                "blocker_node": "29",
                "time_bucket": "6",
                "leg_type": "storage_out",
            },
        ],
    )
    _write_csv(
        root / report.I1_EFFECTS,
        [
            {"effect_label": "BENEFICIAL", "diagnostic_split": "train", "system_cost_delta_seconds": -2.0},
            {"effect_label": "HARMFUL", "diagnostic_split": "validation", "system_cost_delta_seconds": 1.0},
            {"effect_label": "NEUTRAL", "diagnostic_split": "calibration", "system_cost_delta_seconds": 0.0},
        ],
    )
    aliasing = {
        "legacy": {"conditional_variance": 4.0, "sign_disagreement_rate": 0.5},
        "augmented": {"conditional_variance": 1.0, "sign_disagreement_rate": 0.1},
    }
    aliasing_path = root / report.ALIASING_REPORT
    aliasing_path.parent.mkdir(parents=True, exist_ok=True)
    aliasing_path.write_text(f"# audit\n\n```json\n{json.dumps(aliasing)}\n```\n", encoding="utf-8")

    ladder_rows = []
    for segments in report.LADDER_SEGMENTS:
        ladder_rows.append(
            {
                "candidate_id": "D3_LEARNED",
                "policy_family": "learned",
                "segments": segments,
                "candidate_status": "COMPLETE",
                "off_status": "COMPLETE",
                "comparison_status": "MATCHED_COMPLETE",
                "mean_tth_delta_seconds": -0.2,
                "p50_tth_delta_seconds": -0.1,
                "p95_tth_delta_seconds": -0.1,
                "p99_tth_delta_seconds": 0.0,
                "source_wait_delta_mean_seconds": -0.15,
                "network_time_delta_mean_seconds": -0.05,
                "ladder_gate_pass": "True",
            }
        )
    _write_csv(root / report.LADDER_TABLE, ladder_rows)

    scale_rows = []
    for scale in report.SCALE_FACTORS:
        scale_rows.append(
            {
                "candidate_id": "D3_LEARNED",
                "policy_family": "learned",
                "scale": scale,
                "status": "COMPLETE",
                "mean_tth_seconds": 10.0 + scale,
                "p95_tth_seconds": 20.0 + scale,
                "p99_tth_seconds": 30.0 + scale,
                "wall_seconds": 1.5 * scale,
                "peak_rss_mb": 100.0 + scale,
                "high_load_non_regression": "True" if scale in {2, 4, 8} else "False",
            }
        )
    _write_csv(root / report.SCALE_TABLE, scale_rows)

    fault_rows = []
    for load in report.FAULT_LOADS:
        for index, category in enumerate(report.FAULT_CATEGORIES):
            fault_rows.append(
                {
                    "candidate_id": "D3_LEARNED",
                    "policy_family": "learned",
                    "scale": load,
                    "scenario_id": f"{category}_{load}",
                    "fault_category": category,
                    "status": "COMPLETE",
                    "fault_affected_bag_count": 4,
                    "fault_recovery_time_seconds": 5.0,
                    "fault_onset_seconds": 100.0 + index,
                    "repair_time_seconds": 103.0 + index,
                    report.INFLIGHT_MERGE_RECOVERY_COUNTER: (
                        1 if category == "merge_edge_or_node" else 0
                    ),
                    f"{report.INFLIGHT_MERGE_RECOVERY_COUNTER}_available": "True",
                    "fault_gate_pass": "True",
                    "mean_tth_delta_vs_fault_off_seconds": -0.1,
                }
            )
    _write_csv(root / report.FAULT_TABLE, fault_rows)


def _write_g2_no_support_screen(root: Path) -> None:
    comparisons = []
    for segments in report.G2_SCREEN_SEGMENTS:
        for rule in report.G2_SCREEN_RULES:
            comparisons.append(
                {
                    "segments": segments,
                    "baseline_rule": "M1",
                    "candidate_rule": rule,
                    "baseline_exact_competitive_boundary_count": 0,
                    "candidate_exact_competitive_boundary_count": 0,
                    "hard_safety_pass": True,
                    "same_state_causal_opportunity_count": 0,
                    "screen_status": "INSUFFICIENT_MATCHED_CONTENTION",
                    "performance": {
                        "mean_tth_delta_seconds": 0.0,
                        "source_wait_delta_mean_seconds": 0.0,
                        "network_time_delta_mean_seconds": 0.0,
                    },
                }
            )
    _write_json(
        root / report.G2_MATCHED_PILOT,
        {
            "status": "COMPLETE_MATCHED_SCREEN",
            "evidence_kind": "MATCHED_SYSTEM_LOCAL_RULE_SCREEN_NOT_SAME_STATE_CAUSAL",
            "comparison_count": 20,
            "comparisons": comparisons,
            "recommended_for_same_state_causal_followup": [],
            "causal_authorization": {
                "authorized": False,
                "same_state_causal_opportunity_count": 0,
            },
        },
    )


def test_missing_inputs_are_visible_and_never_promoted(tmp_path: Path) -> None:
    result = report.generate_evidence(root=tmp_path, dpi=60)

    assert len(result["figures"]) == 10
    assert all((tmp_path / row["path"]).is_file() for row in result["figures"])
    assert all(row["status"] == "NOT_RUN/NO_EVIDENCE" for row in result["figures"])
    assert result["final"]["decision"].startswith("NOT_RUN/NO_EVIDENCE")
    final = (tmp_path / report.FINAL_REPORT).read_text(encoding="utf-8")
    index = (tmp_path / report.EVIDENCE_INDEX).read_text(encoding="utf-8")
    assert "A–E DECISION DEFERRED" in final
    assert "LEARNED_LOCAL_FLOW_CONTROL_PROMOTED" not in final
    assert "## Publication boundary" in index
    assert "intentionally not distributed with the repository" in index
    assert "compact publication evidence" in index


def test_baseline_only_ladder_uses_manifest_terminal_decision(
    tmp_path: Path,
) -> None:
    manifest = _complete_manifest()
    manifest["stages"]["closed_loop_ladder"] = {
        "status": "COMPLETE",
        "decision": report.BASELINE_ONLY_LADDER_DECISION,
    }
    _write_csv(
        tmp_path / report.LADDER_TABLE,
        [
            {
                "record_type": "TRACK_STATUS",
                "status": "COMPLETE",
                "decision": report.BASELINE_ONLY_LADDER_DECISION,
                "authorized_candidate_count": 0,
                "matched_comparison_row_count": 0,
            }
        ],
    )

    ladder = report._ladder_status(  # noqa: SLF001
        report._read_csv(tmp_path / report.LADDER_TABLE),  # noqa: SLF001
        stage=manifest["stages"]["closed_loop_ladder"],
    )

    assert ladder["status"] == report.BASELINE_ONLY_LADDER_DECISION
    assert ladder["workflow_terminal"] is True
    assert ladder["matrix_complete"] is False
    report._write_final_report(  # noqa: SLF001
        tmp_path,
        manifest,
        ladder,
        {"status": "COMPLETE", "matrix_complete": True},
        {"status": "COMPLETE", "matrix_complete": True},
        {
            "decision": "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT",
            "next_pivot": report.G2_NEXT_PIVOT,
            "causal_gate_pass": False,
        },
    )
    final = (tmp_path / report.FINAL_REPORT).read_text(encoding="utf-8")
    assert report.BASELINE_ONLY_LADDER_DECISION in final


def test_scale_report_forbids_inference_from_unavailable_queue_peaks(
    tmp_path: Path,
) -> None:
    _write_csv(
        tmp_path / report.SCALE_TABLE,
        [
            {
                "candidate_id": "E4_OFF",
                "scale": 1,
                "status": "COMPLETE",
                "mean_tth_seconds": 10.0,
                "p95_tth_seconds": 20.0,
                "wall_seconds": 1.0,
                "peak_rss_mb": 100.0,
                "queue_fields_available": False,
                "source_queue_peak": "",
                "junction_queue_peak": "",
            }
        ],
    )

    report._write_scale_report(tmp_path)  # noqa: SLF001

    text = (tmp_path / report.SCALE_REPORT).read_text(encoding="utf-8")
    assert "**0/1** required scale rows" in text
    assert "queue_fields_available=false" in text
    assert "must not be inferred" in text


def test_scale_report_counts_partial_queue_telemetry_without_claiming_a_bound(
    tmp_path: Path,
) -> None:
    _write_csv(
        tmp_path / report.SCALE_TABLE,
        [
            {
                "candidate_id": "E4_OFF",
                "scale": 1,
                "status": "COMPLETE",
                "queue_fields_available": False,
                "max_source_queue_length": "",
                "max_junction_queue_length": "",
            },
            {
                "candidate_id": "E4_OFF",
                "scale": 16,
                "status": "HARD_GATE_FAILED",
                "queue_fields_available": True,
                "max_source_queue_length": 49116,
                "max_junction_queue_length": 32,
            },
        ],
    )

    result = report._write_scale_report(tmp_path)  # noqa: SLF001

    text = (tmp_path / report.SCALE_REPORT).read_text(encoding="utf-8")
    assert "**1/2** required scale rows" in text
    assert "cross-scale queue-peak bound must not be inferred" in text
    assert result["queue_telemetry_available_rows"] == 1
    assert result["queue_telemetry_required_rows"] == 2
    assert result["queue_peak_bound_supported"] is False


def test_evidence_index_states_publication_boundary_without_plotting(
    tmp_path: Path,
) -> None:
    report._write_index(  # noqa: SLF001
        tmp_path,
        (),
        {"decision": "NOT_RUN/NO_EVIDENCE — TEST"},
        {"matched_screen": {"available": False}},
    )

    index = (tmp_path / report.EVIDENCE_INDEX).read_text(encoding="utf-8")
    assert "## Publication boundary" in index
    assert "outputs/runstate/**" in index
    assert "intentionally not distributed with the repository" in index
    assert "compact publication evidence" in index


def test_capacity_censor_is_terminal_but_does_not_unlock_final_no_go() -> None:
    rows: list[dict[str, object]] = []
    for category in report.FAULT_CATEGORIES:
        rows.append(
            {
                "candidate_id": "E4_OFF",
                "scale": 1,
                "fault_category": category,
                "status": "COMPLETE",
                "fault_gate_pass": True,
            }
        )
        rows.append(
            {
                "candidate_id": "E4_OFF",
                "scale": 4,
                "fault_category": category,
                "status": report.CAPACITY_CENSOR_TREATMENT_STATUS,
                "fault_gate_pass": None,
            }
        )
    rows.append(
        {
            "candidate_id": "E4_OFF",
            "scale": 4,
            "fault_category": "no_fault",
            "status": report.CAPACITY_CENSOR_CONTROL_STATUS,
            "fault_gate_pass": False,
        }
    )

    fault = report._fault_status(rows)  # noqa: SLF001
    assert fault["status"] == report.CAPACITY_CENSOR_TRACK_STATUS
    assert fault["workflow_terminal"] is True
    assert fault["protocol_amended"] is True
    assert fault["scientific_matrix_complete"] is False
    assert fault["matrix_complete"] is False
    assert fault["advantage_supported"] is False

    final = report._final_decision(  # noqa: SLF001
        {
            "final_joint_decision": {
                "decision": report.CAPACITY_CENSOR_FINAL_DECISION,
                "reason": "4x capacity-censored",
                "next_pivot": "bounded-local pivot",
            }
        },
        {"matrix_complete": False},
        {"matrix_complete": True},
        fault,
        {"next_pivot": "fallback pivot"},
    )
    assert final["decision"] == report.CAPACITY_CENSOR_FINAL_DECISION
    assert final["terminal"] is True
    assert final["complete"] is False
    assert final["protocol_amended"] is True
    assert final["scientific_matrix_complete"] is False
    assert "FULL_NO_GO" not in final["decision"]

    unknown_pivot = report._final_decision(  # noqa: SLF001
        {
            "final_joint_decision": {
                "decision": report.CAPACITY_CENSOR_FINAL_DECISION,
                "reason": "4x capacity-censored",
                "next_pivot": "UNKNOWN",
            }
        },
        {"matrix_complete": False},
        {"matrix_complete": True},
        fault,
        {"next_pivot": "bounded-local fallback pivot"},
    )
    assert unknown_pivot["next_pivot"] == "bounded-local fallback pivot"


def test_full_evidence_renders_every_required_plot_and_promotes_only_from_gates(tmp_path: Path) -> None:
    _populate_full_evidence(tmp_path)
    result = report.generate_evidence(root=tmp_path, dpi=60)

    assert {row["key"] for row in result["figures"]} == set(report.FIGURE_PATHS)
    assert all(row["status"] == "EVIDENCE" for row in result["figures"])
    assert result["ladder"]["matrix_complete"] is True
    assert result["scale"]["matrix_complete"] is True
    assert result["fault"]["matrix_complete"] is True
    assert result["fault"]["inflight_merge_recovery_count"] == 2
    assert result["fault"]["inflight_merge_recovery_available_cells"] == len(
        report.FAULT_LOADS
    ) * len(report.FAULT_CATEGORIES)
    fault_report = (tmp_path / report.FAULT_REPORT).read_text(encoding="utf-8")
    assert "Observed exact in-flight merge-generation recoveries: **2**" in fault_report
    assert "In-flight merge recovery" in fault_report
    assert result["final"]["decision"] == "A. LEARNED_LOCAL_FLOW_CONTROL_PROMOTED"


def test_phase_a_g2_trigger_is_not_misreported_as_causal_authorization(tmp_path: Path) -> None:
    manifest = _complete_manifest()
    manifest["stages"]["closed_loop_ladder"]["status"] = "IN_PROGRESS"
    _write_json(tmp_path / report.MANIFEST, manifest)
    result = report.generate_evidence(root=tmp_path, dpi=50)

    assert result["g2"]["triggered"] is True
    assert result["g2"]["causal_gate_pass"] is False
    assert result["g2"]["decision"] == "G2_TRIGGERED_BUT_CAUSAL_PILOT_NOT_RUN"
    g2 = (tmp_path / report.G2_REPORT).read_text(encoding="utf-8")
    assert "causal authorization gate: **NOT_RUN/NO_EVIDENCE**" in g2
    assert "source wait **+0.150000 s/raw bag**" in g2


def test_g2_zero_action_screen_is_seam_no_support_not_rule_success(tmp_path: Path) -> None:
    _write_json(tmp_path / report.MANIFEST, _complete_manifest())
    _write_g2_no_support_screen(tmp_path)

    result = report.generate_evidence(root=tmp_path, dpi=50)

    assert result["g2"]["decision"] == "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT"
    assert result["g2"]["status"] == "NO_SUPPORT_EVIDENCE"
    assert result["g2"]["scope_status"] == report.G2_EAGER_DIAGNOSTIC_STATUS
    assert result["g2"]["global_g2_scientific_no_go"] is False
    assert result["g2"]["causal_gate_pass"] is False
    assert result["g2"]["matched_screen"]["comparison_count"] == 20
    assert result["g2"]["matched_screen"]["all_exact_competitive_boundaries_zero"] is True
    assert result["g2"]["matched_screen"]["all_mean_tth_deltas_zero"] is True
    assert result["g2"]["matched_screen"]["all_mean_decomposition_deltas_zero"] is True
    assert result["g2"]["matched_screen"]["hard_safety_pass_count"] == 20
    assert result["g2"]["matched_screen"]["causal_followup_shortlist_count"] == 0

    g2 = (tmp_path / report.G2_REPORT).read_text(encoding="utf-8")
    index = (tmp_path / report.EVIDENCE_INDEX).read_text(encoding="utf-8")
    final = (tmp_path / report.FINAL_REPORT).read_text(encoding="utf-8")
    for text in (g2, index):
        assert "144, 512, 2,048, 8,192" in text
        assert "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT" in text
        assert "not evidence" in text
        assert report.G2_NEXT_PIVOT in text
    assert report.G2_EAGER_DIAGNOSTIC_STATUS in g2
    assert "not a global G2 scientific no-go" in g2
    assert "FALSE / NOT AUTHORIZED" in final
    assert "aggregate-interval granularity" in final
    assert report.G2_NEXT_PIVOT in final


def test_parser_exposes_root_dpi_and_json() -> None:
    args = report.build_parser().parse_args(["--root", "example", "--dpi", "90", "--json"])
    assert args.root == Path("example")
    assert args.dpi == 90
    assert args.json is True
