from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf25_native_campaign as campaign


def test_observe_artifact_uses_eight_exact_canonical_corridors() -> None:
    artifact = campaign.build_observe_artifact()

    assert artifact["schema"] == "czr005.g4irsf25.clcr.v1"
    assert artifact["mode"] == "observe"
    assert artifact["record_trajectories"] is True
    assert len(artifact["feature_names"]) == 21
    assert [
        (arm["branch_node"], arm["first_edge"], arm["rejoin_node"])
        for arm in artifact["arms"]
    ] == [
        (6, 8, 13),
        (6, 12, 13),
        (9, 7, 14),
        (9, 10, 14),
        (16, 17, 24),
        (16, 21, 24),
        (19, 18, 26),
        (19, 25, 26),
    ]
    assert [arm["corridor_nodes"] for arm in artifact["arms"]] == [
        [6, 8, 11, 13],
        [6, 12, 13],
        [9, 7, 8, 11, 14],
        [9, 10, 15, 14],
        [16, 17, 18, 22, 24],
        [16, 21, 23, 24],
        [19, 18, 22, 26],
        [19, 25, 26],
    ]
    assert [arm["static_duration_seconds"] for arm in artifact["arms"]] == [
        17.2,
        14.0,
        20.400000000000002,
        24.0,
        24.0,
        29.200000000000003,
        18.0,
        17.2,
    ]
    assert [arm["support"] for arm in artifact["arms"]] == [
        2962,
        3996,
        6202,
        599,
        9699,
        576,
        2443,
        42,
    ]


def test_run_plan_is_balanced_and_starts_not_measured() -> None:
    specs = campaign.build_run_plan(
        {"T0": "t0", "L1": "l1"},
        screen_sizes=(144, 512, 8192),
        full_scales=(1, 2),
        bounded_seconds=(60.0, 180.0),
    )

    one_x = [row for row in specs if row["workload"] == "scale_1x"]
    two_x = [row for row in specs if row["workload"] == "scale_2x"]
    assert [row["arm"] for row in one_x] == ["S4", "T0", "L1", "L1", "T0", "S4"]
    assert [row["arm"] for row in two_x] == ["T0", "L1", "S4", "S4", "L1", "T0"]
    bounded = [row for row in specs if row["execution_mode"] == "bounded"]
    assert {row["bounded_wall_seconds"] for row in bounded} == {60.0, 180.0}
    assert {row["family"] for row in specs} == {"BASELINE", "THRESHOLD", "LEARNING"}
    assert all(campaign._unmeasured_run(row)["status"] == campaign.NOT_MEASURED for row in specs)


def _trajectory(
    *,
    scale: int,
    edge: int,
    duration: float | None,
    path: list[int],
    timeout: bool = False,
    censored: bool = False,
    censor_reason: str = "",
) -> dict[str, object]:
    assert not (timeout and censored)
    return {
        "scale": scale,
        "branch_node": 6,
        "selected_first_edge": edge,
        "rejoin_node": 13,
        "completed_rejoin": not timeout and not censored,
        "timeout": timeout,
        "censored": censored,
        "censor_reason": censor_reason,
        "loop": False,
        "safe": True,
        "intermediate_decision_count": 1,
        "actual_path": path,
        "actual_corridor_duration": duration,
        "private_bag_cost_seconds": duration,
        "corridor_wait_seconds": 2.0,
        "local_queue_area_bag_seconds": 3.0,
    }


def test_trajectory_coverage_distinguishes_zero_from_unrun() -> None:
    artifact = campaign.build_observe_artifact()
    rows = [
        _trajectory(scale=1, edge=8, duration=10.0, path=[6, 8, 11, 13]),
        _trajectory(scale=1, edge=8, duration=14.0, path=[6, 8, 11, 13]),
        _trajectory(
            scale=1,
            edge=12,
            duration=None,
            path=[6, 12],
            timeout=True,
        ),
        _trajectory(
            scale=1,
            edge=12,
            duration=None,
            path=[6, 12],
            censored=True,
            censor_reason="BAG_COMPLETED_BEFORE_REJOIN",
        ),
        _trajectory(
            scale=1,
            edge=12,
            duration=None,
            path=[6, 12],
            censored=True,
            censor_reason="BAG_COMPLETED_BEFORE_REJOIN",
        ),
        _trajectory(
            scale=1,
            edge=12,
            duration=None,
            path=[6, 12],
            censored=True,
            censor_reason="RUNTIME_STOP",
        ),
    ]
    run_rows = [
        {"scale": 1, "status": "COMPLETE", "evidence_status": "MEASURED_COMPLETE"},
        {
            "scale": 2,
            "status": campaign.NOT_MEASURED,
            "evidence_status": campaign.NOT_MEASURED,
        },
    ]

    coverage = campaign.aggregate_trajectories(
        rows,
        expected_arms=artifact["arms"],
        run_rows=run_rows,
    )

    assert coverage["status"] == "MEASURED"
    assert coverage["measured_scales"] == [1]
    assert coverage["trajectory_count"] == 6
    assert coverage["completed_rejoin_count"] == 2
    assert coverage["timeout_count"] == 1
    assert coverage["censored_count"] == 3
    assert coverage["trajectory_count"] == (
        coverage["completed_rejoin_count"]
        + coverage["timeout_count"]
        + coverage["censored_count"]
    )
    assert len(coverage["coverage"]) == 8
    arm_8 = next(
        row
        for row in coverage["coverage"]
        if row["branch_node"] == 6 and row["first_edge"] == 8
    )
    assert arm_8["trajectory_count"] == 2
    assert arm_8["actual_corridor_duration_seconds"]["mean"] == 12.0
    arm_12 = next(
        row
        for row in coverage["coverage"]
        if row["branch_node"] == 6 and row["first_edge"] == 12
    )
    assert arm_12["trajectory_count"] == 4
    assert arm_12["completed_rejoin_count"] == 0
    assert arm_12["timeout_count"] == 1
    assert arm_12["censored_count"] == 3
    assert arm_12["censor_reasons"] == {
        "BAG_COMPLETED_BEFORE_REJOIN": 2,
        "RUNTIME_STOP": 1,
    }
    arm_17 = next(
        row
        for row in coverage["coverage"]
        if row["branch_node"] == 16 and row["first_edge"] == 17
    )
    assert arm_17["trajectory_count"] == 0
    assert arm_17["actual_corridor_duration_seconds"]["mean"] == campaign.NOT_MEASURED


def test_plan_only_persists_literal_not_measured_rows(tmp_path: Path) -> None:
    artifact = campaign.build_observe_artifact()
    artifact["mode"] = "t0"
    artifact["record_trajectories"] = False
    artifact["t0_enter_pressure"] = 2.0
    artifact["t0_exit_pressure"] = 1.0
    output_json = tmp_path / "plan.json"
    output_csv = tmp_path / "plan.csv"
    native_report = tmp_path / "native.md"
    scale_csv = tmp_path / "scale.csv"
    scale_report = tmp_path / "scale.md"

    payload = campaign.execute_campaign(
        binary=Path(__file__),
        release_csv=Path(__file__),
        artifacts={"T0": artifact},
        output_json=output_json,
        output_csv=output_csv,
        native_report=native_report,
        scale_csv=scale_csv,
        scale_report=scale_report,
        screen_sizes=(144,),
        full_scales=(),
        bounded_seconds=(),
        plan_only=True,
    )

    stored = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["measured_run_count"] == 0
    assert stored["not_measured_run_count"] == 2
    assert all(row["processed_attempt_mean_seconds"] == campaign.NOT_MEASURED for row in stored["runs"])
    assert campaign.NOT_MEASURED in output_csv.read_text(encoding="utf-8")
    native_text = native_report.read_text(encoding="utf-8")
    assert all(policy in native_text for policy in ("S4", "T0", "L1", "L2", "L3"))
    assert campaign.NOT_MEASURED in native_text
    assert scale_csv.is_file()
    scale_text = scale_report.read_text(encoding="utf-8")
    assert "60s" in scale_text and "180s" in scale_text
    assert "no HCA or G24-static value is synthesized" in scale_text


def _complete_full_row(row: dict[str, object], *, mean: float, mutations: int) -> None:
    row.update(
        status="COMPLETE",
        evidence_status="MEASURED_COMPLETE",
        processed_attempt_mean_seconds=mean,
        processed_attempt_p95_seconds=mean + 10.0,
        processed_attempt_p99_seconds=mean + 20.0,
        processed_attempt_max_seconds=mean + 30.0,
        committed_mutations=mutations,
        safety_pass=True,
    )


def test_balanced_full_summary_never_uses_an_incomplete_repeat() -> None:
    specs = campaign.build_run_plan(
        {"T0": "t0"}, screen_sizes=(), full_scales=(1,), bounded_seconds=()
    )
    rows = [campaign._unmeasured_run(spec) for spec in specs]
    s4_rows = [row for row in rows if row["mode"] == "off"]
    t0_rows = [row for row in rows if row["mode"] == "t0"]
    _complete_full_row(s4_rows[0], mean=100.0, mutations=0)
    _complete_full_row(s4_rows[1], mean=102.0, mutations=0)
    _complete_full_row(t0_rows[0], mean=90.0, mutations=5)

    s4 = campaign._balanced_full_summary(rows, mode="off", scale=1)
    incomplete_t0 = campaign._balanced_full_summary(rows, mode="t0", scale=1)

    assert s4["status"] == "MEASURED_BALANCED_REPEATS"
    assert s4["processed_attempt_mean_seconds"] == 101.0
    assert incomplete_t0["status"] == campaign.NOT_MEASURED
    assert incomplete_t0["processed_attempt_mean_seconds"] == campaign.NOT_MEASURED
    assert incomplete_t0["committed_mutations"] == campaign.NOT_MEASURED

    _complete_full_row(t0_rows[1], mean=92.0, mutations=7)
    complete_t0 = campaign._balanced_full_summary(rows, mode="t0", scale=1)
    assert complete_t0["status"] == "MEASURED_BALANCED_REPEATS"
    assert complete_t0["processed_attempt_mean_seconds"] == 91.0
    assert complete_t0["committed_mutations"] == 12


def test_scale_report_keeps_bounded_progress_measured_but_tth_not_measured() -> None:
    specs = campaign.build_run_plan(
        {}, screen_sizes=(), full_scales=(), bounded_seconds=(60.0, 180.0)
    )
    rows = [campaign._unmeasured_run(spec) for spec in specs]
    sixty = next(row for row in rows if row["bounded_wall_seconds"] == 60.0)
    sixty.update(
        status="BOUNDED_PROGRESS",
        evidence_status="MEASURED_BOUNDED_PROGRESS",
        segments_requested=100,
        segments_released=70,
        segments_completed=50,
        current_backlog=20,
        events_per_completed_segment=12.5,
        committed_mutations=4,
        safety_pass=True,
    )

    summary = campaign._bounded_scale_summary(rows, mode="off", duration=60.0)
    report = campaign._scale_report(rows)

    assert summary["completion_fraction"] == 0.5
    assert summary["processed_attempt_mean_seconds"] == campaign.NOT_MEASURED
    assert "50.000%" in report
    assert "70/100" in report and "50/100" in report
    assert campaign.NOT_MEASURED in report


def test_bounded_payload_without_bag_rows_uses_progress_only() -> None:
    spec = campaign.build_run_plan(
        {}, screen_sizes=(), full_scales=(), bounded_seconds=(60.0,)
    )[0]
    rows = [{"segment_id": f"seg-{index}"} for index in range(4)]
    payload = {
        "execution_status": "BOUNDED_PROGRESS",
        "summary": {
            "event_count": 50,
            "max_junction_queue_length": 7,
            "max_source_queue_length": 3,
        },
        "progress": {
            "wall_seconds": 60.0,
            "requested_bags": 4,
            "released_bags": 3,
            "completed_bags": 2,
            "failed_bags": 0,
            "current_backlog": 1,
            "event_total": 50,
        },
    }

    result = campaign._summarize_payload(
        spec,
        rows=rows,
        payload=payload,
        wall_seconds=60.0,
        cpu_seconds=12.0,
        active=False,
    )

    assert result["status"] == "BOUNDED_PROGRESS"
    assert result["evidence_status"] == "MEASURED_BOUNDED_PROGRESS"
    assert result["segments_released"] == 3
    assert result["segments_completed"] == 2
    assert result["current_backlog"] == 1
    assert result["event_count"] == 50
    assert result["events_per_completed_segment"] == 25.0
    assert result["deadline_miss_count"] == campaign.NOT_MEASURED
    assert result["raw_bags_completed"] == campaign.NOT_MEASURED
    assert result["processed_attempt_count"] == campaign.NOT_MEASURED
    assert result["processed_attempt_mean_seconds"] == campaign.NOT_MEASURED
    assert result["processed_attempt_p95_seconds"] == campaign.NOT_MEASURED
    assert result["processed_attempt_p99_seconds"] == campaign.NOT_MEASURED
    assert result["processed_attempt_max_seconds"] == campaign.NOT_MEASURED


def test_full_payload_still_requires_bag_rows() -> None:
    spec = campaign.build_run_plan(
        {}, screen_sizes=(), full_scales=(1,), bounded_seconds=()
    )[0]

    with pytest.raises(campaign.G25CampaignError, match="full native payload lacks bag rows"):
        campaign._summarize_payload(
            spec,
            rows=[{"segment_id": "seg-0"}],
            payload={"summary": {}},
            wall_seconds=1.0,
            cpu_seconds=0.5,
            active=False,
        )


def test_screen_gate_requires_exact_complete_screens_and_active_signal() -> None:
    empty = campaign._screen_stage_gates([], ["T0"])
    assert empty["S4"]["passed"] is False
    assert empty["T0"]["passed"] is False
    assert "MISSING_PREFIX_144" in empty["T0"]["not_measured_reason"]

    specs = campaign.build_run_plan(
        {"T0": "t0"},
        screen_sizes=campaign.SCREEN_SIZES,
        full_scales=(),
        bounded_seconds=(),
    )
    rows = [campaign._unmeasured_run(spec) for spec in specs]
    for row in rows:
        row.update(
            status="COMPLETE",
            evidence_status="MEASURED_COMPLETE",
            safety_pass=True,
            committed_mutations=0,
            fallbacks=1 if row["arm"] == "T0" else 0,
        )

    zero_mutation = campaign._screen_stage_gates(rows, ["T0"])
    assert zero_mutation["S4"]["passed"] is True
    assert zero_mutation["T0"]["passed"] is False
    assert zero_mutation["T0"]["not_measured_reason"] == "SCREEN_GATE_FAILED:ZERO_MUTATIONS"

    next(row for row in rows if row["arm"] == "T0")["committed_mutations"] = 1
    passed = campaign._screen_stage_gates(rows, ["T0"])
    assert passed["T0"]["passed"] is True
    for row in rows:
        if row["arm"] == "T0":
            row["fallbacks"] = 0
    zero_fallback = campaign._screen_stage_gates(rows, ["T0"])
    assert zero_fallback["T0"]["not_measured_reason"] == "SCREEN_GATE_FAILED:ZERO_FALLBACKS"


def _fake_measured_run(spec: dict[str, object]) -> dict[str, object]:
    row = campaign._unmeasured_run(spec)
    bounded = spec["execution_mode"] == "bounded"
    row.update(
        status="BOUNDED_PROGRESS" if bounded else "COMPLETE",
        evidence_status=(
            "MEASURED_BOUNDED_PROGRESS" if bounded else "MEASURED_COMPLETE"
        ),
        not_measured_reason="",
        safety_pass=True,
        committed_mutations=0,
        fallbacks=0,
        segments_requested=100,
        segments_released=80,
        segments_completed=60,
        current_backlog=20,
        events_per_completed_segment=10.0,
        processed_attempt_mean_seconds=100.0,
        processed_attempt_p95_seconds=110.0,
        processed_attempt_p99_seconds=120.0,
        processed_attempt_max_seconds=130.0,
    )
    if spec["arm"] == "T0" and spec["execution_mode"] == "screen_full":
        row["fallbacks"] = 2
    return row


def test_formal_campaign_gates_failed_active_arm_and_persists_provenance_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = campaign.build_observe_artifact()
    artifact["mode"] = "t0"
    calls: list[tuple[str, str]] = []

    def fake_load(spec: dict[str, object], _release: Path) -> tuple[list[dict[str, object]], dict[str, object], None]:
        return ([{"fixture": True}], {"protocol": "fixture", "topology_changed": False}, None)

    def fake_execute(spec: dict[str, object], **_kwargs: object) -> tuple[dict[str, object], list[dict[str, object]]]:
        calls.append((str(spec["arm"]), str(spec["execution_mode"])))
        return _fake_measured_run(spec), []

    monkeypatch.setattr(campaign, "_load_workload", fake_load)
    monkeypatch.setattr(campaign, "_execute_native", fake_execute)
    outputs = {
        "output_json": tmp_path / "campaign.json",
        "output_csv": tmp_path / "closed.csv",
        "native_report": tmp_path / "native.md",
        "scale_csv": tmp_path / "scale.csv",
        "scale_report": tmp_path / "scale.md",
    }
    payload = campaign.execute_campaign(
        binary=Path(__file__),
        release_csv=Path(__file__),
        artifacts={"T0": artifact},
        artifact_paths={"T0": Path(__file__)},
        screen_sizes=campaign.SCREEN_SIZES,
        full_scales=(1,),
        bounded_seconds=(60.0,),
        **outputs,
    )

    assert payload["screen_stage_gates"]["S4"]["passed"] is True
    assert payload["screen_stage_gates"]["T0"]["not_measured_reason"] == "SCREEN_GATE_FAILED:ZERO_MUTATIONS"
    assert not any(arm == "T0" and stage != "screen_full" for arm, stage in calls)
    skipped = [
        row
        for row in payload["runs"]
        if row["arm"] == "T0" and row["execution_mode"] != "screen_full"
    ]
    assert skipped and all(row["status"] == campaign.NOT_MEASURED for row in skipped)
    assert all(row["evidence_status"] == campaign.NOT_MEASURED for row in skipped)
    assert {row["not_measured_reason"] for row in skipped} == {"SCREEN_GATE_FAILED:ZERO_MUTATIONS"}
    assert payload["measured_run_count"] == 9
    assert payload["not_measured_run_count"] == 3
    executed_t0 = next(
        row for row in payload["runs"] if row["arm"] == "T0" and row["workload"] == "prefix_144"
    )
    assert executed_t0["release_csv"].endswith("tests/test_g4irsf25_native_campaign.py")
    assert executed_t0["artifact_label"] == "T0" and executed_t0["artifact_mode"] == "t0"
    assert executed_t0["artifact_path"].endswith("tests/test_g4irsf25_native_campaign.py")
    assert executed_t0["workload_descriptor"] == {"protocol": "fixture", "topology_changed": False}
    assert all(path.is_file() for path in outputs.values())
    assert not list(tmp_path.glob(".*.tmp"))


def test_measured_predicate_controls_counts_and_trajectory_zero_fill() -> None:
    rows = []
    for evidence in (
        "INCOMPLETE_TTH_NOT_MEASURED",
        "MEASURED_COMPLETE",
        "MEASURED_BOUNDED_PROGRESS",
    ):
        row = campaign._unmeasured_run(
            {
                "run_id": evidence,
                "arm": "S4",
                "mode": "off",
                "family": "BASELINE",
                "workload": "scale_1x",
                "scale": 1,
                "execution_mode": "full",
                "repeat": 0,
                "order_index": 0,
                "bounded_wall_seconds": campaign.NOT_MEASURED,
            }
        )
        row.update(status="FULL_GATE_FAILED", evidence_status=evidence)
        rows.append(row)
    document = campaign._campaign_document(rows, Path(__file__), Path(__file__))
    assert document["attempted_run_count"] == 3
    assert document["measured_run_count"] == 2
    assert document["not_measured_run_count"] == 1

    arms = campaign.build_observe_artifact()["arms"]
    incomplete = campaign.aggregate_trajectories(
        [], expected_arms=arms, run_rows=[{"scale": 1, "evidence_status": "INCOMPLETE_TTH_NOT_MEASURED"}]
    )
    measured_zero = campaign.aggregate_trajectories(
        [], expected_arms=arms, run_rows=[{"scale": 1, "evidence_status": "MEASURED_COMPLETE"}]
    )
    assert incomplete["status"] == campaign.NOT_MEASURED and incomplete["coverage"] == []
    assert measured_zero["status"] == "MEASURED"
    assert len(measured_zero["coverage"]) == 8
    assert all(row["trajectory_count"] == 0 for row in measured_zero["coverage"])


def test_formal_start_failure_does_not_overwrite_existing_canonical_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [
        tmp_path / "campaign.json",
        tmp_path / "closed.csv",
        tmp_path / "native.md",
        tmp_path / "scale.csv",
        tmp_path / "scale.md",
    ]
    for path in paths:
        path.write_text("previous-canonical", encoding="utf-8")

    def fail_load(_spec: object, _release: object) -> object:
        raise campaign.G25CampaignError("fixture startup failure")

    monkeypatch.setattr(campaign, "_load_workload", fail_load)
    with pytest.raises(campaign.G25CampaignError, match="startup failure"):
        campaign.execute_campaign(
            binary=Path(__file__),
            release_csv=Path(__file__),
            artifacts={},
            output_json=paths[0],
            output_csv=paths[1],
            native_report=paths[2],
            scale_csv=paths[3],
            scale_report=paths[4],
            screen_sizes=(144,),
            full_scales=(),
            bounded_seconds=(),
        )

    assert all(path.read_text(encoding="utf-8") == "previous-canonical" for path in paths)
