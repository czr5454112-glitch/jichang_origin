from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf29_native as g29


def _rows() -> list[dict[str, object]]:
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


def _workload_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    rows = _rows()
    monkeypatch.setattr(g29, "FULL_RAW_BAGS", 3)
    monkeypatch.setattr(g29, "FULL_SEGMENTS", 4)
    canonical = tmp_path / "canonical.jsonl"
    canonical.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": g29.WORKLOAD_SCHEMA,
                "status": "COMPLETE",
                "protocol": g29.WORKLOAD_PROTOCOL,
                "raw_task_count": 3,
                "expanded_segment_count": 4,
            }
        ),
        encoding="utf-8",
    )
    return canonical, manifest


def _hca_files(
    tmp_path: Path,
    rows: list[dict[str, object]],
    *,
    released_ids: set[str] | None = None,
    case_id: str = "t5_2_speed_2p5",
    speed_mps: float = 2.5,
    fault_schedule: str = "none",
) -> tuple[Path, Path]:
    released = released_ids or {str(row["segment_id"]) for row in rows}
    case_root = tmp_path / case_id
    run_dir = case_root / "run_01"
    run_dir.mkdir(parents=True)
    (case_root / "case_protocol.json").write_text(
        json.dumps(
            {
                "schema": g29.HCA_CASE_PROTOCOL_SCHEMA,
                "case": {
                    "case_id": case_id,
                    "speed_mps": speed_mps,
                    "fault_schedule": fault_schedule,
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
    metrics = run_dir / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "schema": "g4irsf24.fresh_hca.metrics.v1",
                "canonical_segment_count": len(rows),
                "canonical_raw_bag_count": len(
                    {int(row["task_id"]) for row in rows}
                ),
                "released_segment_count": len(released),
                "planned_segment_count": len(released),
                "completed_segment_count": len(released),
                "canonical_complete_raw_bag_count": 2,
                "canonical_incomplete_raw_bag_count": 1,
                "canonical_success_rate": 2 / 3,
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


def _admitted_artifact(case_id: str) -> dict[str, object]:
    return {
        "schema": g29.SCHEMA,
        "status": g29.COMPLETE,
        "case_id": case_id,
        "selection": {"mode": "full"},
        "fixed_horizon": {
            "required": True,
            "expected_max_simulation_time": g29.FIXED_HORIZON,
            "request_max_simulation_time": g29.FIXED_HORIZON,
            "summary_declared_max_simulation_time": g29.FIXED_HORIZON,
            "pass": True,
        },
    }


def test_registered_matrix_is_4_plus_12_plus_15() -> None:
    assert len(g29._STABLE_IDS) == 4
    assert len(g29._BIAS_CASES) == 12
    assert len(g29._FAULT_IDS) == 15
    assert len(g29.CASE_IDS) == 31
    assert "t5_5_fault_pair_5_7" not in g29.CASE_IDS


def test_release_sources_match_speed_and_faults_use_no_fault_2p5() -> None:
    stable = g29.release_source_contract(g29.resolve_case("t5_2_speed_1p5"))
    bias = g29.release_source_contract(
        g29.resolve_case("t5_4_bias_std_3_dev_20")
    )
    fault = g29.release_source_contract(g29.resolve_case(g29._FAULT_IDS[0]))

    assert stable["source_case_id"] == "t5_2_speed_1p5"
    assert bias["source_case_id"] == "t5_2_speed_3"
    assert fault["source_case_id"] == "t5_2_speed_2p5"
    assert fault["expected_fault_schedule"] == "none"
    assert fault["comparison_scope"] == (
        "fixed_population_fault_capacity_not_segment_paired"
    )
    assert g29.default_hca_run_dir(g29._FAULT_IDS[0]) == (
        g29.DEFAULT_HCA_ROOT / "t5_2_speed_2p5" / "run_01"
    )


def test_earliest_canary_keeps_every_leg_of_selected_raw_bag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)

    prefix, _manifest, selection = g29.load_workload(
        canonical, manifest, earliest_raw_bags=1
    )

    assert prefix.raw_bag_count == 1
    assert prefix.size_segments == 2
    assert {row["segment_id"] for row in prefix.rows} == {"early-in", "early-out"}
    assert selection["whole_raw_bags_retained"] is True
    assert selection["ordering"] == "min(original_entry_time),task_id"


def test_mechanical_segment_copy_manifest_is_not_accepted_as_g29(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["protocol"] = "MECHANICAL_EXPANDED_SEGMENT_COPY_2X"
    manifest.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(g29.Native29Error, match="schedule-preserving"):
        g29.load_workload(canonical, manifest, earliest_raw_bags=1)


def test_incomplete_hca_full_release_blocks_before_native_and_keeps_capacity_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)
    lifecycle, metrics = _hca_files(
        tmp_path,
        _rows(),
        released_ids={"early-in", "early-out", "middle-direct"},
    )

    result = g29.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
    )

    assert result["status"] == g29.BLOCKED_RELEASE
    assert result["native_execution_started"] is False
    assert result["exact_release_gate"]["pass"] is False
    assert result["exact_release_gate"]["survivor_only_full_claim_allowed"] is False
    assert result["exact_release_gate"][
        "full_population_capacity_comparison_allowed"
    ] is False
    assert result["hca_capacity_view"]["released_segment_count"] == 3
    assert result["hca_capacity_view"]["expected_segment_count"] == 4


def test_canary_requires_only_selected_whole_bag_release_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)
    lifecycle, metrics = _hca_files(
        tmp_path,
        _rows(),
        released_ids={"early-in", "early-out"},
    )

    result = g29.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        earliest_raw_bags=1,
        dry_run=True,
    )

    assert result["status"] == g29.DRY_RUN_READY
    assert result["selection"]["selected_raw_bag_count"] == 1
    assert result["selection"]["selected_segment_count"] == 2
    assert result["exact_release_gate"]["mode"] == "EXACT_PAIRED_CANARY"
    assert result["policy_contract"]["service_aware_static_local_potential"] is True
    assert result["policy_contract"]["learning_active"] is False


def test_fault_rejects_fault_hca_release_instead_of_misclaiming_pairing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)
    fault_case = g29._FAULT_IDS[0]
    lifecycle, metrics = _hca_files(
        tmp_path,
        _rows(),
        case_id=fault_case,
        speed_mps=2.5,
        fault_schedule="8260:6:12:fault",
    )

    result = g29.execute_case(
        fault_case,
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        earliest_raw_bags=1,
        dry_run=True,
    )

    assert result["status"] == g29.BLOCKED_RELEASE
    assert result["release_source_contract"]["source_case_id"] == (
        "t5_2_speed_2p5"
    )
    assert result["exact_release_gate"]["release_source_gates"][
        "source_case_id"
    ] is False
    assert result["native_execution_started"] is False


def test_fault_uses_no_fault_2p5_full_release_without_timing_pair_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)
    lifecycle, metrics = _hca_files(tmp_path, _rows())

    result = g29.execute_case(
        g29._FAULT_IDS[0],
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=None,
        dry_run=True,
    )

    assert result["status"] == g29.DRY_RUN_READY
    assert result["exact_release_gate"]["mode"] == (
        "REFERENCE_RELEASE_FULL_NON_PAIRED_FAULT"
    )
    assert result["exact_release_gate"][
        "full_outcome_timing_comparison_allowed"
    ] is False
    assert result["release_source_contract"]["comparison_scope"] == (
        "fixed_population_fault_capacity_not_segment_paired"
    )


def test_incomplete_fault_timing_is_not_measured_and_keeps_fixed_denominator() -> None:
    timing = g29.timing_evidence(
        g29.resolve_case(g29._FAULT_IDS[0]),
        _prefix(_rows()),
        (),
        {
            "selected_raw_bag_count": 3,
            "completed_raw_bag_count": 2,
            "success": {
                "primary_completed_raw_bags": {
                    "count": 2,
                    "rate": 2 / 3,
                    "definition": "all_selected_segments_completed",
                }
            },
        },
        {"full_outcome_timing_comparison_allowed": False},
    )

    assert timing["status"] == "NOT_MEASURED"
    assert timing["completed_raw_bag_count"] == 2
    assert timing["fixed_population_success"]["rate"] == pytest.approx(2 / 3)
    assert timing["full_outcome_timing_comparison_allowed"] is False


def test_prepare_bias_reuses_g27_g28_and_only_injects_fixed_bias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supplied = _prefix(_rows()[:1])
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    captured: dict[str, object] = {}

    def fake_prepare(case, prefix, *, binary, service_aware_potential):
        captured.update(
            case=case,
            prefix=prefix,
            binary=binary,
            service_aware_potential=service_aware_potential,
        )
        return (
            {
                "scorer_mode": "S4_queue_aware_rule_only",
                "merge_grant_timing_mode": "jit_fair_aging_deadline",
                "g4irsf20_event_hotpath_policy": "E2",
                "queue_discipline": "fifo",
            },
            tuple(prefix.rows),
            (),
            {
                "artifact": None,
                "service_aware_potential": {"enabled": True},
            },
        )

    monkeypatch.setattr(g29.g27_fault, "prepare_request", fake_prepare)
    resolved = g29.resolve_case("t5_4_bias_std_2p5_dev_20")

    request, runtime_rows, rejected, _local = g29.prepare_native_request(
        resolved, supplied, binary=binary, canary=True
    )

    assert captured["service_aware_potential"] is True
    assert len(runtime_rows) == 1 and rejected == ()
    assert request["legacy_observation_bias_max_seconds"] == pytest.approx(2.0)
    assert request["legacy_observation_bias_seed"] == g29.g27_bias.FIXED_OBSERVATION_BIAS_SEED
    assert request["scenario"].endswith("_canary")

    for full_case_id in (
        "t5_2_speed_2p5",
        "t5_4_bias_std_2p5_dev_20",
        g29._FAULT_IDS[0],
    ):
        full_request, *_ = g29.prepare_native_request(
            g29.resolve_case(full_case_id), supplied, binary=binary, canary=False
        )
        assert full_request["max_simulation_time"] == g29.FIXED_HORIZON
        assert full_request["scenario"].endswith("_full")


def _safe_summary(completed: int) -> dict[str, object]:
    summary: dict[str, object] = {
        name: 0 for name in g24.HARD_SAFETY_ZERO_FIELDS
    }
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
        declared_max_simulation_time=g29.FIXED_HORIZON,
    )
    return summary


def test_exact_full_executes_registered_local_stack_with_fixed_population(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, manifest = _workload_files(tmp_path, monkeypatch)
    lifecycle, metrics = _hca_files(tmp_path, _rows())
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")

    def fake_prepare(resolved, prefix, *, binary, canary):
        return (
            {
                "bag_records": harness.binding_bag_records(prefix),
                "max_simulation_time": g29.FIXED_HORIZON,
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

    monkeypatch.setattr(g29, "prepare_native_request", fake_prepare)
    result = g29.execute_case(
        "t5_2_speed_2p5",
        canonical_path=canonical,
        manifest_path=manifest,
        lifecycle_path=lifecycle,
        metrics_path=metrics,
        binary=binary,
        executor=fake_executor,
    )

    assert result["status"] == g29.COMPLETE
    assert result["fixed_horizon"]["pass"] is True
    assert result["exact_release_gate"]["pass"] is True
    assert result["exact_release_gate"][
        "full_outcome_timing_comparison_allowed"
    ] is True
    assert result["selection"]["selected_raw_bag_count"] == 3
    assert result["outcome"]["completed_raw_bag_count"] == 3
    assert result["timing"]["status"] == "MEASURED"
    assert set(result["timing"]["distributions"]) == {
        "processed_attempt",
        "java_release",
        "original_entry",
    }
    for distribution in result["timing"]["distributions"].values():
        assert set(distribution) == {
            "count",
            "min_seconds",
            "p50_seconds",
            "mean_seconds",
            "p95_seconds",
            "p99_seconds",
            "max_seconds",
        }
    assert result["timing"]["distributions"]["processed_attempt"][
        "mean_seconds"
    ] == pytest.approx(20 / 3)
    assert result["timing"]["display_aliases"] == {
        "original_entry": "raw_entry"
    }
    assert result["safety"]["pass"] is True
    assert result["runtime"]["event_count"] == 123


def test_resume_skips_existing_case_without_reading_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "case.json"
    output.write_text(
        json.dumps(_admitted_artifact("t5_2_speed_2p5")),
        encoding="utf-8",
    )

    code = g29.main(
        [
            "case",
            "--case-id",
            "t5_2_speed_2p5",
            "--hca-run-dir",
            str(tmp_path / "missing-hca"),
            "--output",
            str(output),
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "SKIPPED_EXISTING"


def test_resume_lane_skips_complete_runs_remaining_and_writes_aggregate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = g29._STABLE_IDS[:2]
    case_root = tmp_path / "lane"
    case_root.mkdir()
    (case_root / f"{first}.json").write_text(
        json.dumps(_admitted_artifact(first)),
        encoding="utf-8",
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    calls: list[tuple[str, Path]] = []

    def fake_execute(case_id, **kwargs):
        calls.append((case_id, kwargs["lifecycle_path"]))
        return _admitted_artifact(case_id)

    monkeypatch.setattr(g29, "execute_case", fake_execute)
    code = g29.main(
        [
            "resume",
            "--case-id",
            first,
            "--case-id",
            second,
            "--case-root",
            str(case_root),
            "--binary",
            str(binary),
        ]
    )

    assert code == 0
    assert calls == [
        (
            second,
            g29.default_hca_run_dir(second) / "segment_lifecycle.csv",
        )
    ]
    assert json.loads(
        (case_root / f"{second}.json").read_text(encoding="utf-8")
    )["status"] == g29.COMPLETE
    aggregate = json.loads(
        (case_root / g29.RESUME_AGGREGATE_NAME).read_text(encoding="utf-8")
    )
    assert aggregate["schema"] == g29.AGGREGATE_SCHEMA
    assert {first, second}.issubset(aggregate["complete_case_ids"])


def test_resume_lane_reruns_stale_complete_without_fixed_horizon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = g29._STABLE_IDS[0]
    case_root = tmp_path / "lane"
    case_root.mkdir()
    stale = {
        "schema": g29.SCHEMA,
        "status": g29.COMPLETE,
        "case_id": case_id,
        "selection": {"mode": "full"},
    }
    (case_root / f"{case_id}.json").write_text(
        json.dumps(stale), encoding="utf-8"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    calls: list[str] = []

    def fake_execute(selected, **_kwargs):
        calls.append(selected)
        return _admitted_artifact(selected)

    monkeypatch.setattr(g29, "execute_case", fake_execute)
    code = g29.main(
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
    refreshed = json.loads(
        (case_root / f"{case_id}.json").read_text(encoding="utf-8")
    )
    assert refreshed["fixed_horizon"]["pass"] is True


def test_resume_lane_stops_on_blocked_case_before_next_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = g29._STABLE_IDS[:2]
    case_root = tmp_path / "lane"
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"")
    calls: list[str] = []

    def fake_execute(case_id, **_kwargs):
        calls.append(case_id)
        return {
            "schema": g29.SCHEMA,
            "status": g29.BLOCKED_RELEASE,
            "case_id": case_id,
        }

    monkeypatch.setattr(g29, "execute_case", fake_execute)
    code = g29.main(
        [
            "resume",
            "--case-id",
            first,
            "--case-id",
            second,
            "--case-root",
            str(case_root),
            "--binary",
            str(binary),
        ]
    )

    assert code == 2
    assert calls == [first]
    assert not (case_root / f"{second}.json").exists()
    aggregate = json.loads(
        (case_root / g29.RESUME_AGGREGATE_NAME).read_text(encoding="utf-8")
    )
    assert aggregate["blocked_release_case_ids"] == [first]


def test_aggregate_is_partial_until_all_registered_cases_are_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = g29._STABLE_IDS[:2]
    monkeypatch.setattr(g29, "CASE_IDS", (first, second))
    for case_id, status in (
        (first, g29.COMPLETE),
        (second, g29.BLOCKED_RELEASE),
    ):
        value = _admitted_artifact(case_id)
        value["status"] = status
        if case_id == first:
            value["exact_release_gate"] = {
                "lifecycle_path": str(
                    g29.ROOT / "outputs/runtime/g4irsf29_hca/example.csv"
                )
            }
        (tmp_path / f"{case_id}.json").write_text(
            json.dumps(value),
            encoding="utf-8",
        )

    partial = g29.aggregate_results(tmp_path)
    assert partial["status"] == "PARTIAL"
    assert partial["blocked_release_case_ids"] == [second]
    assert partial["cases"][0]["exact_release_gate"]["lifecycle_path"] == (
        "outputs/runtime/g4irsf29_hca/example.csv"
    )

    (tmp_path / f"{second}.json").write_text(
        json.dumps(_admitted_artifact(second)),
        encoding="utf-8",
    )
    complete = g29.aggregate_results(tmp_path)
    assert complete["status"] == "COMPLETE"
    assert complete["complete_case_ids"] == sorted((first, second))
    assert "not_segment_paired_fault_timings" in complete["claim_boundary"]
