from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import aggregate_cie_service_normalization as aggregate
from scripts.eval import run_cie_service_normalization as runner


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"service-normalization-test-binary")
    workload_1x = tmp_path / "map2_1x.jsonl"
    workload_2x = tmp_path / "map2_2x.jsonl"
    workload_1x.write_text("{}\n", encoding="utf-8")
    workload_2x.write_text("{}\n{}\n", encoding="utf-8")
    values: dict[str, object] = {
        "map": "map2",
        "scale": 1,
        "arm": "RAW_COUNT_AS_SECONDS",
        "service_condition": "REAL_SERVICE",
        "release_mode": "canonical",
        "binary": binary,
        "output": tmp_path / "out.json",
        "revision_manifest": runner.REVISION_MANIFEST,
        "nanning_task_dir": tmp_path,
        "nanning_map_profile": tmp_path / "nanning.json",
        "nanning_hca_root": tmp_path,
        "map2_workload_1x": workload_1x,
        "map2_workload_2x": workload_2x,
        "map2_hca_case_root": None,
        "dry_run": True,
        "force": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _base_request(binary: Path) -> dict[str, object]:
    return {
        "node_records": [
            [0, 0, 0.5, 0.0, 0.0, [1, 2]],
            [1, 0, 2.0, 1.0, 0.0, [2]],
            [2, 0, 1.0, 2.0, 0.0, []],
        ],
        "edge_records": [
            [0, 1, 1.0, 1.0],
            [1, 2, 1.0, 1.0],
            [0, 2, 5.0, 1.0],
        ],
        "heuristic_time": [
            [0.0, 1.5, 4.5],
            [999.0, 0.0, 3.0],
            [999.0, 999.0, 0.0],
        ],
        "bag_records": [["1:direct", 1, 0.0, 100.0, 0, 2, "node_0"]],
        "minimum_service_seconds": 0.001,
        "scorer_mode": "S4_queue_aware_rule_only",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "complete_on_goal_arrival": True,
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "g4irsf20_event_hotpath_policy": "E2",
        "max_events": runner.g35.nanning_native.MAX_EVENTS,
        "max_simulation_time": runner.g35.nanning_native.FIXED_END_EPOCH,
        "expected_binary_path": str(binary.resolve()),
    }


def _patch_prepare(
    monkeypatch: pytest.MonkeyPatch, args: argparse.Namespace
) -> SimpleNamespace:
    workload = SimpleNamespace(
        raw_bag_count=1,
        segment_count=1,
        rows=(
            {
                "segment_id": "1:direct",
                "task_id": 1,
                "pass_time": 0.0,
                "original_entry_time": 0.0,
                "std": 100.0,
                "start": 0,
                "goal": 2,
            },
        ),
        source_path=Path(args.map2_workload_1x),
    )
    release = {
        "mode": "canonical",
        "same_hca_release_trace_pass": False,
        "formal_same_hca_release_input": False,
        "request_delta_from_g31": {},
        "removed_request_fields_from_g31": [],
    }
    monkeypatch.setattr(
        runner.g35,
        "_prepare",
        lambda _args: (
            "t5_2_map2_1x_speed_2p5",
            workload,
            _base_request(Path(args.binary)),
            release,
        ),
    )
    return workload


@pytest.mark.parametrize(
    ("arm", "scaling", "mask", "changed"),
    [
        ("RAW_COUNT_AS_SECONDS", "raw_count_as_seconds", 15, []),
        (
            "SERVICE_RATE_NORMALIZED",
            "service_rate_normalized",
            15,
            ["queue_time_scaling"],
        ),
        (
            "NO_QI_BUT_CALENDAR",
            "raw_count_as_seconds",
            12,
            ["s4_score_component_mask"],
        ),
    ],
)
def test_three_arms_use_only_existing_exact_request_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arm: str,
    scaling: str,
    mask: int,
    changed: list[str],
) -> None:
    args = _args(tmp_path, arm=arm)
    _patch_prepare(monkeypatch, args)
    monkeypatch.setattr(
        runner.cpp_backend,
        "g4irsf11_event_runtime_from_records",
        lambda **_request: pytest.fail("dry-run invoked native runtime"),
    )

    result = runner.execute(args)

    contract = result["service_normalization_contract"]
    assert result["status"] == "READY_CIE_SERVICE_NORMALIZATION_DRY_RUN"
    assert result["native_execution_started"] is False
    assert result["algorithm"]["queue_time_scaling"] == scaling
    assert result["algorithm"]["s4_score_component_mask"] == mask
    assert contract["arm_delta_from_raw_reference"] == changed
    assert contract["calendar_semantics"]["new_native_mode_added"] is False
    if arm == "NO_QI_BUT_CALENDAR":
        assert contract["component_enabled"] == {
            "Q": False,
            "I": False,
            "wc": True,
            "ws": True,
        }
        assert contract["calendar_semantics"][
            "direct_neighbor_calendar_visibility_retained"
        ] is True
        assert contract["calendar_semantics"][
            "physical_service_calendar_not_controlled_by_score_mask"
        ] is True


def test_service_x2_perturbs_all_shared_nodes_and_rebuilds_h_sa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _args(tmp_path, service_condition="SERVICE_X2")
    _patch_prepare(monkeypatch, args)
    original = _base_request(Path(args.binary))

    _case, _workload, request, _release, contract = runner.prepare_cell(args)

    assert [row[2] for row in request["node_records"]] == [1.0, 4.0, 2.0]
    assert request["edge_records"] == original["edge_records"]
    assert request["bag_records"] == original["bag_records"]
    assert request["heuristic_time"] != original["heuristic_time"]
    service = contract["service_control"]
    assert service["service_time_multiplier"] == 2.0
    assert service["changed_request_fields_before_h_sa_rebuild"] == [
        "node_records"
    ]
    assert service["goal_union_was_not_globally_excluded"] is True
    assert service[
        "same_node_remains_perturbed_when_transit_for_another_bag"
    ] is True
    assert contract["potential"]["rebuilt_after_service_control"] is True

    real_args = _args(tmp_path, service_condition="REAL_SERVICE")
    _patch_prepare(monkeypatch, real_args)
    _case, _workload, _request, _release, real_contract = runner.prepare_cell(
        real_args
    )
    assert (
        contract["cross_service_condition_identity_sha256"]
        == real_contract["cross_service_condition_identity_sha256"]
    )


def test_manifest_must_preserve_frozen_service_control(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "frozen_before_formal_result_read: true\n"
        "service_heterogeneity_control:\n"
        "  construction: multiply_existing_non_goal_service_time\n"
        "  multiplier: 2.5\n"
        "  topology_tasks_and_release_unchanged: true\n",
        encoding="utf-8",
    )

    with pytest.raises(runner.ServiceNormalizationError, match="frozen contract"):
        runner.load_service_control(manifest)


def test_native_echoes_are_required_without_changing_metrics_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _args(tmp_path, arm="NO_QI_BUT_CALENDAR", dry_run=False)
    workload = _patch_prepare(monkeypatch, args)
    monkeypatch.setattr(
        runner.factorial,
        "_paper_subjects",
        lambda *_args, **_kwargs: (
            {"pass": True, "gates": {"base": True}},
            {
                "fixed_horizon_capacity": {
                    "formal_fixed_horizon_eligible": True
                },
                "full_population_raw_bag_timing": {
                    "status": "FULL_POPULATION_RAW_BAG_TIMING",
                    "raw_bag_count": 1,
                    "survivor_or_common_cohort_used": False,
                    "metrics_seconds": {
                        "paper_network_from_admission": {
                            "min": 1.0,
                            "mean": 1.0,
                            "p95": 1.0,
                            "p99": 1.0,
                            "max": 1.0,
                        }
                    },
                },
            },
        ),
    )
    monkeypatch.setattr(
        runner.cie_business,
        "summarize",
        lambda rows, bags, *, fixed_horizon: {
            "denominator_raw_bags": len(workload.rows),
            "fixed_denominator": True,
            "survivor_or_common_cohort_used": False,
        },
    )
    summary = {
        "queue_time_scaling": "raw_count_as_seconds",
        "s4_score_component_mask": 12,
        "s4_local_potential_descent_guard_enabled": True,
        "s4_direct_neighbor_merge_calendar_visibility_enabled": True,
        "complete_on_goal_arrival_enabled": True,
        "event_count": 2,
        "decision_count": 1,
        "loaded_cpp_binary_sha256": runner._file_sha256(Path(args.binary)),
    }

    result = runner.execute(
        args, executor=lambda **_request: {"summary": summary, "bags": []}
    )

    assert result["status"] == "COMPLETE"
    assert result["execution_integrity"]["pass"] is True
    assert result["paper_subjects"]["full_population_raw_bag_timing"][
        "survivor_or_common_cohort_used"
    ] is False


def test_wrong_loaded_binary_sha_fails_execution_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _args(tmp_path, dry_run=False)
    _patch_prepare(monkeypatch, args)
    monkeypatch.setattr(
        runner.factorial,
        "_paper_subjects",
        lambda *_args, **_kwargs: (
            {"pass": True, "gates": {"base": True}},
            {
                "fixed_horizon_capacity": {
                    "formal_fixed_horizon_eligible": True
                },
                "full_population_raw_bag_timing": {
                    "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
                    "raw_bag_count": None,
                    "metrics_seconds": None,
                },
            },
        ),
    )
    monkeypatch.setattr(
        runner.cie_business,
        "summarize",
        lambda *_args, **_kwargs: {},
    )
    summary = {
        "queue_time_scaling": "raw_count_as_seconds",
        "s4_score_component_mask": 15,
        "s4_local_potential_descent_guard_enabled": True,
        "s4_direct_neighbor_merge_calendar_visibility_enabled": True,
        "complete_on_goal_arrival_enabled": True,
        "loaded_cpp_binary_sha256": "wrong",
    }

    result = runner.execute(
        args, executor=lambda **_request: {"summary": summary, "bags": []}
    )

    assert result["status"] == "FAILED_INTEGRITY"
    assert result["execution_integrity"]["gates"][
        "loaded_cpp_binary_sha256_echo"
    ] is False


def _aggregate_payload(
    *,
    arm: str,
    mean: float,
    condition: str = "REAL_SERVICE",
    identity: str = "same-comparison",
    cross_condition_identity: str = "same-cross-condition-base",
    status: str = "COMPLETE",
) -> dict[str, object]:
    expected = runner.ARMS[arm]
    integrity = status == "COMPLETE"
    return {
        "schema": runner.SCHEMA,
        "native_execution_started": True,
        "status": status,
        "map": "map2",
        "scale": 1,
        "service_condition": condition,
        "population": {"raw_bag_count": 10, "segment_count": 10},
        "release_protocol": {"mode": "canonical"},
        "binary": {"sha256": "binary"},
        "provenance": {"workload_sha256": "workload"},
        "algorithm": {
            "policy": "s4_service_normalization_specialty",
            "policy_label": "G31_S4_NATIVE_SERVICE_NORMALIZATION_SPECIALTY",
            "arm": arm,
            "cell_id": f"{condition}__{arm}",
            "coordination_protocol": "G31_J2_M3",
            "queue_time_scaling": expected["queue_time_scaling"],
            "s4_score_component_mask": expected["s4_score_component_mask"],
        },
        "potential": {"selected": "sa", "selected_label": "H_SA"},
        "service_normalization_contract": {
            "comparison_identity_sha256": identity,
            "cross_service_condition_identity_sha256": cross_condition_identity,
            "no_qi_but_calendar_exact_existing_interface": True,
            "service_control": {
                "service_time_multiplier": (
                    1.0 if condition == "REAL_SERVICE" else 2.0
                )
            },
        },
        "execution_integrity": {"pass": integrity},
        "paper_subjects": {
            "fixed_horizon_capacity": {
                "denominator_raw_bags": 10,
                "completed_raw_bag_count": 10,
                "completion_rate": 1.0,
            },
            "full_population_raw_bag_timing": {
                "status": "FULL_POPULATION_RAW_BAG_TIMING",
                "raw_bag_count": 10,
                "survivor_or_common_cohort_used": False,
                "metrics_seconds": {
                    "paper_network_from_admission": {
                        "min": mean - 5.0,
                        "mean": mean,
                        "p95": mean + 5.0,
                        "p99": mean + 8.0,
                        "max": mean + 10.0,
                    }
                },
            },
            "fixed_denominator_business": {
                "on_time_raw_bag_count": 9,
                "on_time_rate": 0.9,
                "missed_bag_count": 1,
                "missed_bag_rate": 0.1,
                "tardiness_seconds": {
                    "fixed_horizon_all_population_lower_bound": {
                        "sum": mean * 10.0,
                        "mean": mean,
                        "p95": mean + 1.0,
                        "p99": mean + 2.0,
                        "max": mean + 3.0,
                    }
                },
                "completion_targets": {
                    "time_to_90_percent": {
                        "reached": True,
                        "elapsed_from_first_arrival_seconds": mean * 2.0,
                    },
                    "time_to_95_percent": {
                        "reached": True,
                        "elapsed_from_first_arrival_seconds": mean * 3.0,
                    },
                    "time_to_99_percent": {
                        "reached": True,
                        "elapsed_from_first_arrival_seconds": mean * 4.0,
                    },
                },
                "backlog": {
                    "raw_bag_total": {
                        "backlog_area_seconds": mean * 100.0,
                        "peak_backlog": 4,
                        "end_backlog": 0,
                    },
                    "raw_bag_source_until_all_segments_admitted": {
                        "backlog_area_seconds": mean * 30.0,
                        "peak_backlog": 3,
                        "end_backlog": 0,
                    },
                    "raw_bag_network_after_all_segments_admitted": {
                        "backlog_area_seconds": mean * 70.0,
                        "peak_backlog": 2,
                        "end_backlog": 0,
                    },
                },
            },
        },
        "runtime": {
            "wall_seconds": mean / 10.0,
            "cpu_seconds": mean / 11.0,
            "native_summary": {
                "completed_count": 10,
                "event_count": int(mean * 100),
                "decision_count": int(mean * 10),
            },
        },
    }


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_aggregate_writes_exact_three_arm_deltas_and_audit(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    means = {
        "RAW_COUNT_AS_SECONDS": 100.0,
        "SERVICE_RATE_NORMALIZED": 90.0,
        "NO_QI_BUT_CALENDAR": 110.0,
    }
    for arm, mean in means.items():
        _write_payload(
            inputs / f"{arm}.json", _aggregate_payload(arm=arm, mean=mean)
        )
    summary = tmp_path / "summary.csv"
    report = tmp_path / "report.md"

    count, complete_groups = aggregate.aggregate([inputs], summary, report)

    assert count == 3
    assert complete_groups == 1
    rows = list(csv.DictReader(summary.open(encoding="utf-8")))
    mean_row = next(
        row
        for row in rows
        if row["map"] == "map2"
        and row["service_condition"] == "REAL_SERVICE"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert mean_row["comparison_status"] == "COMPLETE"
    assert float(mean_row["normalized_minus_raw"]) == pytest.approx(-10.0)
    assert float(mean_row["normalized_relative_to_raw_percent"]) == pytest.approx(
        -10.0
    )
    assert mean_row["normalized_outcome"] == "IMPROVED"
    assert float(mean_row["no_qi_minus_raw"]) == pytest.approx(10.0)
    assert mean_row["no_qi_outcome"] == "WORSE"
    text = report.read_text(encoding="utf-8")
    assert "mask 12" in text
    assert "no survivor/common cohort" in text


def test_aggregate_does_not_form_contrast_with_failed_or_mismatched_cell(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for arm, mean in (
        ("RAW_COUNT_AS_SECONDS", 100.0),
        ("SERVICE_RATE_NORMALIZED", 90.0),
        ("NO_QI_BUT_CALENDAR", 95.0),
    ):
        payload = _aggregate_payload(arm=arm, mean=mean)
        if arm == "NO_QI_BUT_CALENDAR":
            payload["status"] = "FAILED_INTEGRITY"
            payload["execution_integrity"] = {"pass": False}
        _write_payload(inputs / f"{arm}.json", payload)

    summary = tmp_path / "summary.csv"
    report = tmp_path / "report.md"
    _count, complete_groups = aggregate.aggregate([inputs], summary, report)

    assert complete_groups == 0
    rows = list(csv.DictReader(summary.open(encoding="utf-8")))
    mean_row = next(
        row
        for row in rows
        if row["map"] == "map2"
        and row["service_condition"] == "REAL_SERVICE"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert mean_row["comparison_status"] == "FAILED_CELLS"
    assert mean_row["normalized_minus_raw"] == ""
    assert mean_row["no_qi_minus_raw"] == ""


def test_aggregate_does_not_form_contrast_across_request_identities(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for arm, identity in (
        ("RAW_COUNT_AS_SECONDS", "identity-a"),
        ("SERVICE_RATE_NORMALIZED", "identity-a"),
        ("NO_QI_BUT_CALENDAR", "identity-b"),
    ):
        _write_payload(
            inputs / f"{arm}.json",
            _aggregate_payload(arm=arm, mean=100.0, identity=identity),
        )

    summary = tmp_path / "summary.csv"
    report = tmp_path / "report.md"
    _count, complete_groups = aggregate.aggregate([inputs], summary, report)

    assert complete_groups == 0
    rows = list(csv.DictReader(summary.open(encoding="utf-8")))
    mean_row = next(
        row
        for row in rows
        if row["map"] == "map2"
        and row["service_condition"] == "REAL_SERVICE"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert mean_row["comparison_status"] == "COMPARISON_IDENTITY_MISMATCH"
    assert mean_row["normalized_minus_raw"] == ""


def test_aggregate_rejects_cross_service_condition_base_identity_mismatch(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for condition, base_identity in (
        ("REAL_SERVICE", "real-base"),
        ("SERVICE_X2", "different-base"),
    ):
        for arm in runner.ARMS:
            _write_payload(
                inputs / f"{condition}_{arm}.json",
                _aggregate_payload(
                    arm=arm,
                    mean=100.0,
                    condition=condition,
                    identity=f"{condition}-comparison",
                    cross_condition_identity=base_identity,
                ),
            )

    summary = tmp_path / "summary.csv"
    report = tmp_path / "report.md"
    _count, complete_groups = aggregate.aggregate([inputs], summary, report)

    assert complete_groups == 0
    rows = list(csv.DictReader(summary.open(encoding="utf-8")))
    assert {
        row["comparison_status"]
        for row in rows
        if row["map"] == "map2"
        and row["service_condition"] in {"REAL_SERVICE", "SERVICE_X2"}
    } == {"CROSS_SERVICE_CONDITION_IDENTITY_MISMATCH"}


def test_aggregate_cli_returns_nonzero_until_all_four_groups_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aggregate, "aggregate", lambda *_args: (3, 1))

    assert aggregate.main(
        [
            "--input",
            str(tmp_path),
            "--summary-csv",
            str(tmp_path / "summary.csv"),
            "--report",
            str(tmp_path / "report.md"),
        ]
    ) == 2


def test_aggregate_rejects_duplicate_cell(tmp_path: Path) -> None:
    payload = _aggregate_payload(arm="RAW_COUNT_AS_SECONDS", mean=100.0)
    _write_payload(tmp_path / "one.json", payload)
    _write_payload(tmp_path / "two.json", payload)

    with pytest.raises(
        aggregate.ServiceNormalizationAggregationError, match="duplicate"
    ):
        aggregate.aggregate(
            [tmp_path], tmp_path / "summary.csv", tmp_path / "report.md"
        )
