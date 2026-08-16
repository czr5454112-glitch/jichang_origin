from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf30_native as g30


def _small_rows() -> list[dict[str, object]]:
    return [
        {
            "segment_id": "late-direct",
            "task_id": 30,
            "leg": "direct",
            "original_entry_time": 30.0,
            "pass_time": 30.0,
            "std": 300.0,
            "start": 0,
            "goal": 47,
        },
        {
            "segment_id": "early-in",
            "task_id": 10,
            "leg": "storage_in",
            "original_entry_time": 10.0,
            "pass_time": 10.0,
            "std": 200.0,
            "start": 0,
            "goal": 47,
        },
        {
            "segment_id": "middle-direct",
            "task_id": 20,
            "leg": "direct",
            "original_entry_time": 20.0,
            "pass_time": 20.0,
            "std": 250.0,
            "start": 1,
            "goal": 48,
        },
        {
            "segment_id": "early-out",
            "task_id": 10,
            "leg": "storage_out",
            "original_entry_time": 10.0,
            "pass_time": 40.0,
            "std": 200.0,
            "start": 52,
            "goal": 48,
        },
    ]


def _write_workload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]] | None = None,
) -> tuple[Path, Path]:
    selected = rows or _small_rows()
    raw_count = len({int(row["task_id"]) for row in selected})
    monkeypatch.setattr(g30, "FULL_RAW_BAGS", raw_count)
    monkeypatch.setattr(g30, "FULL_SEGMENTS", len(selected))
    canonical = tmp_path / "canonical.jsonl"
    canonical.write_text(
        "".join(json.dumps(row) + "\n" for row in selected), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": g30.WORKLOAD_SCHEMA,
                "status": "COMPLETE",
                "protocol": g30.WORKLOAD_PROTOCOL,
                "raw_task_count": raw_count,
                "expanded_segment_count": len(selected),
            }
        ),
        encoding="utf-8",
    )
    return canonical, manifest


def _write_hca(
    tmp_path: Path,
    rows: list[dict[str, object]],
    *,
    released_ids: set[str] | None = None,
    case_id: str = "t5_2_speed_2p5",
    speed_mps: float = 2.5,
    fault_schedule: str = "none",
) -> tuple[Path, Path]:
    released = (
        {str(row["segment_id"]) for row in rows}
        if released_ids is None
        else released_ids
    )
    case_root = tmp_path / case_id
    run_dir = case_root / "run_01"
    run_dir.mkdir(parents=True)
    (case_root / "case_protocol.json").write_text(
        json.dumps(
            {
                "schema": g30.HCA_CASE_PROTOCOL_SCHEMA,
                "case": {
                    "case_id": case_id,
                    "speed_mps": speed_mps,
                    "fault_schedule": fault_schedule,
                },
                "fixed_window": {
                    "start_epoch": g30.HCA_START_EPOCH,
                    "max_epochs": g30.HCA_MAX_EPOCHS,
                    "end_epoch": g30.HCA_END_EPOCH,
                },
                "workload": {
                    "protocol": g30.WORKLOAD_PROTOCOL,
                    "raw_task_count": g30.FULL_RAW_BAGS,
                    "expanded_segment_count": g30.FULL_SEGMENTS,
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "run_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "run_id": "run_01",
                "speed_mps": speed_mps,
                "fault_schedule": fault_schedule,
                "start_epoch": g30.HCA_START_EPOCH,
                "max_epochs": g30.HCA_MAX_EPOCHS,
                "returncode": 0,
            }
        ),
        encoding="utf-8",
    )
    lifecycle = run_dir / "segment_lifecycle.csv"
    with lifecycle.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["segment_id", "release_epoch"])
        writer.writeheader()
        for ordinal, row in enumerate(rows):
            if str(row["segment_id"]) in released:
                writer.writerow(
                    {
                        "segment_id": row["segment_id"],
                        "release_epoch": 100.0 + ordinal,
                    }
                )
    raw_count = len({int(row["task_id"]) for row in rows})
    metrics = run_dir / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "schema": "g4irsf24.fresh_hca.metrics.v1",
                "canonical_segment_count": len(rows),
                "canonical_raw_bag_count": raw_count,
                "released_segment_count": len(released),
                "planned_segment_count": len(released),
                "completed_segment_count": len(released),
                "canonical_complete_raw_bag_count": raw_count,
                "canonical_incomplete_raw_bag_count": 0,
                "canonical_success_rate": 1.0,
                "comparison_eligible": len(released) == len(rows),
            }
        ),
        encoding="utf-8",
    )
    return lifecycle, metrics


def _prefix(rows: list[dict[str, object]]) -> harness.InputPrefix:
    return harness.InputPrefix(
        len(rows),
        tuple(dict(row) for row in rows),
        "",
        len({int(row["task_id"]) for row in rows}),
        str(rows[0]["segment_id"]),
        str(rows[-1]["segment_id"]),
    )


def _artifact(case_id: str) -> dict[str, object]:
    return {
        "schema": g30.SCHEMA,
        "status": g30.COMPLETE,
        "case_id": case_id,
        "workload_protocol": g30.WORKLOAD_PROTOCOL,
        "selection": {
            "mode": "full",
            "selected_raw_bag_count": g30.FULL_RAW_BAGS,
            "selected_segment_count": g30.FULL_SEGMENTS,
        },
        "exact_release_gate": {
            "pass": True,
            "mode": "EXACT_PAIRED_FULL",
            "exact_release_applied": True,
            "full_population_capacity_comparison_allowed": True,
        },
        "safety": {"pass": True},
        "fixed_horizon": {
            "required": True,
            "expected_max_simulation_time": g30.FIXED_HORIZON,
            "request_max_simulation_time": g30.FIXED_HORIZON,
            "summary_declared_max_simulation_time": g30.FIXED_HORIZON,
            "pass": True,
        },
        "event_budget": {
            "required": True,
            "expected_max_events": g30.G30_MAX_EVENTS,
            "request_max_events": g30.G30_MAX_EVENTS,
            "summary_declared_max_events": g30.G30_MAX_EVENTS,
            "summary_event_count": 123,
            "summary_event_limit_reached": False,
            "event_limit_not_reached": True,
            "pass": True,
        },
    }


def test_contract_is_3x_and_reuses_the_31_case_matrix() -> None:
    assert g30.FULL_RAW_BAGS == 85_518
    assert g30.FULL_SEGMENTS == 130_809
    assert g30.FIXED_HORIZON == 98_259.0
    assert g30.G30_MAX_EVENTS == 60_000_000
    assert g30.G30_MAX_EVENTS == g30.g26.TABLE_5_5_MAX_EVENTS
    assert g30.COMPLETE_FIXED_HORIZON_CAPACITY in g30.COMPLETE_STATUSES
    assert len(g30.CASE_IDS) == 31
    assert "t5_5_fault_pair_5_7" not in g30.CASE_IDS
    assert g30.default_hca_run_dir(g30.g29._FAULT_IDS[0]) == (
        g30.DEFAULT_HCA_ROOT / "t5_2_speed_2p5" / "run_01"
    )


def test_earliest_512_canary_keeps_every_leg_of_each_raw_bag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows: list[dict[str, object]] = []
    for task_id in range(513):
        rows.append(
            {
                "segment_id": f"{task_id}:direct",
                "task_id": task_id,
                "leg": "direct",
                "original_entry_time": float(task_id),
                "pass_time": float(task_id),
                "std": 10_000.0,
                "start": 0,
                "goal": 47,
            }
        )
    rows.insert(
        1,
        {
            "segment_id": "0:storage_out",
            "task_id": 0,
            "leg": "storage_out",
            "original_entry_time": 0.0,
            "pass_time": 100.0,
            "std": 10_000.0,
            "start": 52,
            "goal": 48,
        },
    )
    canonical, manifest = _write_workload(tmp_path, monkeypatch, rows)

    prefix, _manifest, selection = g30.load_workload(
        canonical, manifest, earliest_raw_bags=512
    )

    assert prefix.raw_bag_count == 512
    assert prefix.size_segments == 513
    assert {row["segment_id"] for row in prefix.rows if row["task_id"] == 0} == {
        "0:direct",
        "0:storage_out",
    }
    assert selection["whole_raw_bags_retained"] is True
    assert selection["requested_earliest_raw_bags"] == 512


def test_non_schedule_preserving_manifest_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _write_workload(tmp_path, monkeypatch)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["protocol"] = "MECHANICAL_SEGMENT_COPY_3X"
    manifest.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(g30.Native30Error, match="schedule-preserving"):
        g30.load_workload(canonical, manifest)


def test_trusted_incomplete_full_hca_uses_own_source_fixed_horizon_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _write_workload(tmp_path, monkeypatch)
    lifecycle, metrics = _write_hca(
        tmp_path,
        _small_rows(),
        released_ids={"early-in", "early-out", "middle-direct"},
    )

    result = g30.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        dry_run=True,
    )

    assert result["status"] == g30.DRY_RUN_READY
    assert result["native_execution_started"] is False
    assert result["exact_release_gate"]["pass"] is True
    assert result["exact_release_gate"]["mode"] == (
        "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
    )
    assert result["exact_release_gate"]["exact_release_applied"] is False
    assert result["exact_release_gate"]["release_pairing"] == "NOT_PAIRED"
    assert result["exact_release_gate"]["arrival_source"] == (
        "canonical_scheduled_pass_time"
    )
    assert result["exact_release_gate"][
        "full_population_capacity_comparison_allowed"
    ] is True
    assert result["exact_release_gate"][
        "full_outcome_timing_comparison_allowed"
    ] is False
    assert result["exact_release_gate"]["survivor_only_full_claim_allowed"] is False
    assert result["hca_capacity_view"]["released_segment_count"] == 3
    assert result["hca_capacity_view"]["expected_segment_count"] == 4

    original, *_ = g30.load_workload(canonical, manifest)
    scheduled, gate, _capacity = g30.apply_hca_release_lifecycle(
        original,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        full_required=True,
        release_contract=g30.release_source_contract(
            g30.g29.resolve_case("t5_2_speed_2p5")
        ),
    )
    assert scheduled is original
    assert [row["pass_time"] for row in scheduled.rows] == [
        row["pass_time"] for row in original.rows
    ]
    assert "alignment" not in gate


def test_incomplete_full_hca_without_fixed_window_trust_still_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _write_workload(tmp_path, monkeypatch)
    lifecycle, metrics = _write_hca(
        tmp_path,
        _small_rows(),
        released_ids={"early-in", "early-out", "middle-direct"},
    )
    protocol_path = lifecycle.parent.parent / "case_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["fixed_window"]["end_epoch"] = g30.HCA_END_EPOCH - 1
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

    result = g30.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        dry_run=True,
    )

    assert result["status"] == g30.BLOCKED_RELEASE
    assert result["exact_release_gate"]["pass"] is False
    assert result["exact_release_gate"]["fixed_population_source_gates"][
        "protocol_end_epoch"
    ] is False


def test_whole_bag_canary_uses_only_selected_release_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _write_workload(tmp_path, monkeypatch)
    lifecycle, metrics = _write_hca(
        tmp_path,
        _small_rows(),
        released_ids={"early-in", "early-out"},
    )

    result = g30.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        earliest_raw_bags=1,
        dry_run=True,
    )

    assert result["status"] == g30.DRY_RUN_READY
    assert result["selection"]["selected_raw_bag_count"] == 1
    assert result["selection"]["selected_segment_count"] == 2
    assert result["policy_contract"]["framework"] == "S4_J2_E2_plus_local_FIFO"
    assert result["policy_contract"]["service_aware_static_local_potential"] is True
    assert result["policy_contract"]["learning_active"] is False


def test_full_request_reuses_g29_stack_and_fixed_horizon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    supplied = _prefix(_small_rows()[:1])
    calls: list[tuple[str, bool]] = []

    def fake_prepare(resolved, prefix, *, binary, canary):
        calls.append((resolved["case_id"], canary))
        return (
            {"scenario": "g4irsf29_old", "max_simulation_time": 1.0},
            tuple(prefix.rows),
            (),
            {"artifact": None, "service_aware_potential": {"enabled": True}},
        )

    monkeypatch.setattr(g30.g29, "prepare_native_request", fake_prepare)
    for case_id in (
        "t5_2_speed_2p5",
        "t5_4_bias_std_2p5_dev_20",
        g30.g29._FAULT_IDS[0],
    ):
        request, *_ = g30.prepare_native_request(
            g30.g29.resolve_case(case_id), supplied, binary=binary, canary=False
        )
        assert request["scenario"] == f"g4irsf30_{case_id}_full"
        assert request["max_simulation_time"] == g30.FIXED_HORIZON
        assert request["max_events"] == g30.G30_MAX_EVENTS
    assert calls == [
        ("t5_2_speed_2p5", False),
        ("t5_4_bias_std_2p5_dev_20", False),
        (g30.g29._FAULT_IDS[0], False),
    ]


def _safe_summary(completed: int) -> dict[str, object]:
    summary: dict[str, object] = {name: 0 for name in g24.HARD_SAFETY_ZERO_FIELDS}
    summary.update({name: False for name in g24.HARD_SAFETY_FALSE_FIELDS})
    summary.update(
        completed_count=completed,
        fault_event_count=0,
        repair_event_count=0,
        event_count=123,
        decision_count=45,
        scorer_mode="S4_queue_aware_rule_only",
        merge_grant_timing_mode="jit_fair_aging_deadline",
        g4irsf20_event_hotpath_policy="E2",
        declared_max_simulation_time=g30.FIXED_HORIZON,
        declared_max_events=g30.G30_MAX_EVENTS,
    )
    return summary


def test_fake_full_executes_with_three_denominators_and_fixed_population(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _write_workload(tmp_path, monkeypatch)
    lifecycle, metrics = _write_hca(tmp_path, _small_rows())
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    observed_releases: list[list[float]] = []

    def fake_prepare(resolved, prefix, *, binary, canary):
        return (
            {
                "bag_records": harness.binding_bag_records(prefix),
                "max_simulation_time": g30.FIXED_HORIZON,
                "max_events": g30.G30_MAX_EVENTS,
            },
            tuple(prefix.rows),
            (),
            {
                "artifact": None,
                "active_policy": {"queue_discipline": "fifo"},
                "service_aware_potential": {"enabled": True},
            },
        )

    def fake_executor(**request):
        observed_releases.append([float(row[2]) for row in request["bag_records"]])
        bags = [
            {
                "segment_id": segment_id,
                "task_id": task_id,
                "completed": True,
                "admitted_time": release,
                "finish_time": release + 5.0,
            }
            for segment_id, task_id, release, _std, _start, _goal, _source in request[
                "bag_records"
            ]
        ]
        return {"summary": _safe_summary(len(bags)), "bags": bags}

    monkeypatch.setattr(g30, "prepare_native_request", fake_prepare)
    result = g30.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=binary,
        executor=fake_executor,
    )

    assert result["status"] == g30.COMPLETE
    assert result["fixed_horizon"]["pass"] is True
    assert result["event_budget"]["pass"] is True
    assert result["event_budget"]["request_max_events"] == g30.G30_MAX_EVENTS
    assert result["event_budget"]["summary_declared_max_events"] == (
        g30.G30_MAX_EVENTS
    )
    assert result["selection"]["selected_raw_bag_count"] == 3
    assert result["outcome"]["completed_raw_bag_count"] == 3
    assert result["timing"]["status"] == "MEASURED"
    assert set(result["timing"]["distributions"]) == {
        "processed_attempt",
        "java_release",
        "original_entry",
    }
    assert result["exact_release_gate"]["exact_release_applied"] is True
    assert observed_releases[-1] == [100.0, 101.0, 102.0, 103.0]

    lifecycle_rows = list(csv.DictReader(lifecycle.read_text(encoding="utf-8").splitlines()))
    with lifecycle.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["segment_id", "release_epoch"])
        writer.writeheader()
        writer.writerows(lifecycle_rows[:-1])
    partial_metrics = json.loads(metrics.read_text(encoding="utf-8"))
    partial_metrics.update(
        released_segment_count=3,
        planned_segment_count=3,
        completed_segment_count=3,
        comparison_eligible=False,
    )
    metrics.write_text(json.dumps(partial_metrics), encoding="utf-8")

    capacity_result = g30.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=binary,
        executor=fake_executor,
    )

    assert capacity_result["status"] == g30.COMPLETE_OWN_SOURCE
    assert capacity_result["comparison_protocol"] == (
        "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
    )
    assert capacity_result["timing"]["status"] == (
        g30.OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE
    )
    assert set(capacity_result["timing"]["distributions"]) == {
        "processed_attempt",
        "java_release",
        "original_entry",
    }
    assert capacity_result["timing"][
        "full_outcome_timing_comparison_allowed"
    ] is False
    assert capacity_result["timing"]["fresh_hca_timing_verdict_allowed"] is False
    assert observed_releases[-1] == [30.0, 10.0, 20.0, 40.0]

    fault_timing = g30._own_source_timing(
        {"group": "fault"},
        capacity_result["outcome"],
        capacity_result["exact_release_gate"],
        capacity_result["timing"],
    )
    assert fault_timing["status"] == "NOT_MEASURED"
    assert "distributions" not in fault_timing


def test_fault_full_uses_2p5_no_fault_release_and_no_timing_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _write_workload(tmp_path, monkeypatch)
    lifecycle, metrics = _write_hca(tmp_path, _small_rows())

    result = g30.execute_case(
        g30.g29._FAULT_IDS[0],
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        dry_run=True,
    )

    assert result["status"] == g30.DRY_RUN_READY
    assert result["exact_release_gate"]["mode"] == (
        "REFERENCE_RELEASE_FULL_NON_PAIRED_FAULT"
    )
    assert result["release_source_contract"]["source_case_id"] == (
        "t5_2_speed_2p5"
    )
    assert result["exact_release_gate"][
        "full_outcome_timing_comparison_allowed"
    ] is False


def test_resume_reruns_stale_case_and_writes_partial_aggregate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = g30.CASE_IDS[0]
    case_root = tmp_path / "lane"
    case_root.mkdir()
    stale = _artifact(case_id)
    stale["selection"]["selected_raw_bag_count"] = g30.FULL_RAW_BAGS - 1
    (case_root / f"{case_id}.json").write_text(
        json.dumps(stale), encoding="utf-8"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    calls: list[str] = []

    def fake_execute(selected, **_kwargs):
        calls.append(selected)
        return _artifact(selected)

    monkeypatch.setattr(g30, "execute_case", fake_execute)
    code = g30.main(
        [
            "resume",
            "--case-id",
            case_id,
            "--case-root",
            str(case_root),
            "--binary",
            str(binary),
        ]
    )

    assert code == 0
    assert calls == [case_id]
    aggregate = json.loads(
        (case_root / g30.RESUME_AGGREGATE_NAME).read_text(encoding="utf-8")
    )
    assert aggregate["status"] == "PARTIAL"
    assert case_id in aggregate["complete_case_ids"]


def test_aggregate_requires_full_admission_and_portabilizes_repo_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = g30.CASE_IDS[:2]
    monkeypatch.setattr(g30, "CASE_IDS", (first, second))
    admitted = _artifact(first)
    admitted["status"] = g30.COMPLETE_OWN_SOURCE
    admitted["exact_release_gate"] = {
        "pass": True,
        "lifecycle_path": str(g30.ROOT / "outputs/runtime/g4irsf30_hca/example.csv"),
        "mode": "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY",
        "exact_release_applied": False,
        "full_population_capacity_comparison_allowed": True,
        "full_outcome_timing_comparison_allowed": False,
    }
    admitted["timing"] = {
        "status": g30.OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE,
        "full_outcome_timing_comparison_allowed": False,
    }
    stale = _artifact(second)
    stale["fixed_horizon"]["pass"] = False
    for value in (admitted, stale):
        (tmp_path / f"{value['case_id']}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    partial = g30.aggregate_results(tmp_path)

    assert partial["status"] == "PARTIAL"
    assert partial["complete_case_ids"] == [first]
    assert partial["stale_admission_case_ids"] == [second]
    assert partial["fixed_horizon_admission"]["pass"] is False
    assert partial["event_budget_admission"]["expected_max_events"] == (
        g30.G30_MAX_EVENTS
    )
    assert partial["event_budget_admission"]["case_evidence"][first][
        "request_max_events"
    ] == g30.G30_MAX_EVENTS
    assert partial["measurement_scope"][
        "own_source_fixed_horizon_capacity_case_ids"
    ] == [first]
    assert partial["measurement_scope"][
        "full_outcome_timing_comparison_allowed_case_ids"
    ] == []
    assert partial["measurement_scope"][
        "own_source_full_population_descriptive_timing_case_ids"
    ] == [first]
    assert partial["cases"][0]["exact_release_gate"]["lifecycle_path"] == (
        "outputs/runtime/g4irsf30_hca/example.csv"
    )


def test_artifact_admission_requires_runtime_evidence_and_mode_match() -> None:
    case_id = g30.CASE_IDS[0]
    exact = _artifact(case_id)
    assert g30._artifact_admitted(exact) is True

    own_source = _artifact(case_id)
    own_source["status"] = g30.COMPLETE_OWN_SOURCE
    own_source["exact_release_gate"] = {
        "pass": True,
        "mode": "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY",
        "exact_release_applied": False,
        "full_population_capacity_comparison_allowed": True,
    }
    assert g30._artifact_admitted(own_source) is True

    own_source["safety"] = {"pass": False}
    assert g30._artifact_admitted(own_source) is False

    exact["exact_release_gate"]["pass"] = False
    assert g30._artifact_admitted(exact) is False
    exact["exact_release_gate"]["pass"] = True
    exact["status"] = g30.COMPLETE_OWN_SOURCE
    assert g30._artifact_admitted(exact) is False

    exact = _artifact(case_id)
    exact["event_budget"]["summary_declared_max_events"] = 20_000_000
    assert g30._artifact_admitted(exact) is False
    exact = _artifact(case_id)
    exact["event_budget"]["summary_event_limit_reached"] = True
    assert g30._artifact_admitted(exact) is False


def _failed_fixed_horizon_artifact(case_id: str) -> dict[str, object]:
    value = _artifact(case_id)
    value["status"] = g30.FAILED
    value["exact_release_gate"] = {
        "pass": True,
        "mode": "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY",
        "exact_release_applied": False,
        "full_population_capacity_comparison_allowed": True,
    }
    source_gates = {name: True for name in g30._STRUCTURAL_SOURCE_GATES}
    source_gates.update(
        g26_fault_horizon_termination_preserved=False,
        runtime_summary_completed_equals_reachable_requested=False,
        runtime_all_returned_segments_completed=False,
        failed_count_zero=False,
        unresolved_deadlock_count_zero=False,
        time_limit_reached_false=False,
    )
    value["safety"] = {
        "pass": False,
        "source_admission": {
            "pass": False,
            "gates": source_gates,
            "terminal_accounting": {
                "selected_segments": g30.FULL_SEGMENTS,
                "runtime_requested_reachable_segments": g30.FULL_SEGMENTS,
                "source_rejected_unreachable_segments": 0,
                "runtime_completed_segments": g30.FULL_SEGMENTS - 10,
                "runtime_failed_segments": 10,
            },
        },
        "runtime_echo_gates": {
            "active_s4_scorer": True,
            "active_j2_timing": True,
            "active_e2_hotpath": True,
        },
        "fault_value_echo": {"pass": True},
        "observation_bias_echo": {"pass": True},
        "topology_gate_pass": True,
    }
    value["outcome"] = {
        "selected_raw_bag_count": g30.FULL_RAW_BAGS,
        "completed_raw_bag_count": g30.FULL_RAW_BAGS - 10,
    }
    value["timing"] = {"status": "NOT_MEASURED"}
    value["runtime"] = {"event_count": 25_000_000}
    return value


def test_fixed_horizon_operational_incompletion_can_be_reclassified(
    tmp_path: Path,
) -> None:
    case_id = g30.CASE_IDS[0]
    artifact = _failed_fixed_horizon_artifact(case_id)
    output = tmp_path / f"{case_id}.json"
    output.write_text(json.dumps(artifact), encoding="utf-8")
    business_before = {
        key: artifact[key] for key in ("outcome", "timing", "runtime")
    }

    assert g30.main(
        ["reclassify", "--case-id", case_id, "--case-root", str(tmp_path)]
    ) == 0

    upgraded = json.loads(output.read_text(encoding="utf-8"))
    assert upgraded["status"] == g30.COMPLETE_FIXED_HORIZON_CAPACITY
    assert upgraded["safety"]["pass"] is True
    admission = upgraded["safety"]["fixed_horizon_capacity_admission"]
    assert admission["pass"] is True
    assert "g26_fault_horizon_termination_preserved" not in admission[
        "required_structural_source_gates"
    ]
    assert upgraded["safety"]["source_admission"]["gates"][
        "g26_fault_horizon_termination_preserved"
    ] is False
    assert admission["operational_outcome"][
        "does_not_veto_capacity_admission"
    ] is True
    assert {key: upgraded[key] for key in business_before} == business_before
    assert upgraded["reclassification"]["business_metrics_changed"] is False
    assert g30._artifact_admitted(upgraded) is True


def test_fixed_horizon_reclassification_still_requires_structural_gates(
    tmp_path: Path,
) -> None:
    case_id = g30.CASE_IDS[0]
    artifact = _failed_fixed_horizon_artifact(case_id)
    artifact["safety"]["source_admission"]["gates"][
        "reservation_conflicts_zero"
    ] = False
    (tmp_path / f"{case_id}.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )

    with pytest.raises(g30.Native30Error, match="does not prove"):
        g30.reclassify_failed_capacity(case_id, tmp_path)


def test_reclassification_checks_full_artifact_before_writing(tmp_path: Path) -> None:
    case_id = g30.CASE_IDS[0]
    artifact = _failed_fixed_horizon_artifact(case_id)
    artifact["event_budget"]["expected_max_events"] = g30.G30_MAX_EVENTS - 1
    output = tmp_path / f"{case_id}.json"
    output.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(g30.Native30Error, match="full G30 admission"):
        g30.reclassify_failed_capacity(case_id, tmp_path)

    assert json.loads(output.read_text(encoding="utf-8")) == artifact
