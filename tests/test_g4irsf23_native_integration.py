"""Fast, non-formal native integration check for the G23 Source seam."""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import (
    assert_canonical_map,
    canonical_graph_records,
)
ROOT = Path(__file__).resolve().parents[1]
PROFILE = "G23_A0_S4_J2_E2"
CENSUS_SCHEMA = "czr005.g4irsf23.source_admission_census.v1"
TARGET_SCHEMA = "czr005.g4irsf23.source_admit_hold_target.v1"


def _backend() -> ModuleType:
    pythonpath_entries = tuple(
        Path(entry)
        for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if entry
    )
    search_paths = dict.fromkeys(
        (
            *pythonpath_entries,
            ROOT / "build-ci" / "python",
            ROOT / "build_g4irsf23_native" / "python",
            ROOT / "build_vs" / "python" / "Release",
            ROOT / "build_nmake" / "python",
        )
    )
    for search_path in search_paths:
        if not search_path.is_dir():
            continue
        try:
            module = cpp_backend.load_cpp_module(search_path)
        except cpp_backend.CppBackendUnavailable:
            continue
        if all(
            callable(getattr(module, name, None))
            for name in (
                "g4irsf23_scan_source_admission_opportunities_from_records",
                "g4irsf15_run_causal_target_pairs_from_records",
            )
        ):
            return module
    message = "a G23-capable czr005_cpp extension is required"
    if os.environ.get("G4IRSF23_REQUIRE_NATIVE") == "1":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _small_native_arguments() -> tuple[object, ...]:
    assert_canonical_map()
    nodes, edges, heuristic = canonical_graph_records()
    bags = [
        ("0:storage_in", 0, 8267.845453, 22200.0, 3, 47, "node_3"),
        ("0:storage_out", 0, 19500.0, 22200.0, 52, 49, "node_52"),
        ("1:storage_in", 1, 8867.845453, 22200.0, 4, 47, "node_4"),
        ("1:storage_out", 1, 19500.0, 22200.0, 52, 49, "node_52"),
        ("2:storage_in", 2, 8875.816299, 22200.0, 5, 47, "node_5"),
        ("2:storage_out", 2, 19500.0, 22200.0, 52, 49, "node_52"),
        ("3:storage_in", 3, 8880.000872, 22200.0, 3, 47, "node_3"),
        ("3:storage_out", 3, 19500.0, 22200.0, 52, 48, "node_52"),
        ("4:storage_in", 4, 9462.482986, 22200.0, 3, 47, "node_3"),
        ("4:storage_out", 4, 19500.0, 22200.0, 52, 49, "node_52"),
        ("5:storage_in", 5, 9470.615484, 23100.0, 4, 47, "node_4"),
        ("5:storage_out", 5, 20400.0, 23100.0, 52, 49, "node_52"),
        ("6:storage_in", 6, 10062.62162, 22200.0, 5, 47, "node_5"),
        ("6:storage_out", 6, 19500.0, 22200.0, 52, 49, "node_52"),
        ("7:storage_in", 7, 10073.28213, 22200.0, 3, 47, "node_3"),
        ("7:storage_out", 7, 19500.0, 22200.0, 52, 49, "node_52"),
    ]
    original_entries = [
        value
        for value in (
            8267.845453,
            8867.845453,
            8875.816299,
            8880.000872,
            9462.482986,
            9470.615484,
            10062.62162,
            10073.28213,
        )
        for _ in range(2)
    ]
    # G23 uses rule-only S4, so the scorer tensors are intentionally empty.
    return (
        nodes,
        edges,
        heuristic,
        bags,
        [],
        [],
        [],
        0.0,
        0.0,
        0.0,
        "",
        original_entries,
    )


def _target(
    opportunity: dict[str, object], *, horizon: str = "H_bag"
) -> dict[str, object]:
    runtime_bag_id = opportunity["runtime_bag_id"]
    return {
        "schema": TARGET_SCHEMA,
        "target_id": f"native-integration:{horizon}",
        "source_group_id": opportunity["source_group_id"],
        "research_profile": PROFILE,
        "kind": "SOURCE_ADMISSION",
        "intervention_kind": "SOURCE_HOLD_ONE_NATURAL_OPPORTUNITY",
        "baseline_action": "ADMIT_NOW",
        "treatment_action": "HOLD_ONE_NATURAL_OPPORTUNITY",
        "expected_action_change_type": "SOURCE_ADMISSION_ONE_OPPORTUNITY_HOLD",
        "horizon": horizon,
        "event_ordinal": opportunity["event_ordinal"],
        "event_time": opportunity["event_time"],
        "event_seq": opportunity["event_seq"],
        "runtime_bag_id": runtime_bag_id,
        "front_runtime_bag_id": runtime_bag_id,
        "node": 52,
        "leg": "storage_out",
        "release_block": opportunity["release_block"],
        "baseline_admit_legal": True,
        "selection_stratum": "non-formal-native-integration",
        "preserve_front_bag": True,
        "max_hold_opportunities": 1,
        "force_a0_after_hold": True,
        "outcome_free": True,
    }


def _h_bag_target(opportunity: dict[str, object]) -> dict[str, object]:
    return _target(opportunity)


def test_native_source_census_and_one_h_bag_pair() -> None:
    backend = _backend()
    arguments = _small_native_arguments()

    census = backend.g4irsf23_scan_source_admission_opportunities_from_records(
        *arguments, PROFILE
    )
    assert census["schema"] == CENSUS_SCHEMA
    assert census["research_profile"] == PROFILE
    assert census["input_request_count"] == 16
    assert census["census_complete"] is False
    assert census["opportunity_count"] == 8
    assert len(census["opportunities"]) == 8
    for opportunity in census["opportunities"]:
        assert opportunity["schema"] == CENSUS_SCHEMA
        assert opportunity["node"] == 52
        assert opportunity["baseline_release"] is True
        assert opportunity["baseline_admit_legal"] is True
        assert opportunity["runtime_bag_id"] == opportunity["front_runtime_bag_id"]
        assert len(opportunity["outcome_free_context"]) == 39

    target = _h_bag_target(dict(census["opportunities"][0]))
    payload = backend.g4irsf15_run_causal_target_pairs_from_records(
        *arguments, [target], PROFILE
    )
    assert len(payload["pairs"]) == 1
    pair = payload["pairs"][0]
    assert pair["pair_status"] == "ACTION_CHANGED_HORIZON_COMPLETE"
    assert pair["action_changed"] is True
    assert pair["same_state_start"] is True
    assert pair["g4irsf23_plain_baseline_replay"] is True
    assert pair["horizon_complete"] is True
    assert pair["baseline_step"]["event_processed"] is True
    assert pair["baseline_step"]["treatment_requested"] is False
    assert pair["baseline_step"]["intervention_applied"] is False
    assert pair["baseline_step"]["changed_action_count"] == 0
    assert pair["baseline_step"]["source_state_sha256"] == (
        pair["source_checkpoint_state_sha256"]
    )
    assert pair["treatment_step"]["source_state_sha256"] == (
        pair["source_checkpoint_state_sha256"]
    )
    assert pair["baseline"]["horizon_complete"] is True
    assert pair["treatment"]["horizon_complete"] is True
    assert pair["treatment_step"]["application_reason"] == (
        "APPLIED_SOURCE_HOLD_ONE_NATURAL_OPPORTUNITY"
    )
    assert pair["treatment_step"]["changed_action_count"] == 1
    assert pair["action_change_certificate"]["valid"] is True
    assert pair["hold_opportunity_count_observed"] == 1
    assert pair["forced_a0_after_hold_observed"] is True
    assert pair["repeated_hold_count_observed"] == 0


def test_native_source_h_system_uses_compact_output_without_losing_effects() -> None:
    backend = _backend()
    arguments = _small_native_arguments()
    census = backend.g4irsf23_scan_source_admission_opportunities_from_records(
        *arguments, PROFILE
    )
    targets = [
        _target(dict(opportunity), horizon="H_system")
        for opportunity in census["opportunities"][:2]
    ]
    for index, target in enumerate(targets):
        target["target_id"] = f"native-integration:H_system:{index}"

    payload = backend.g4irsf15_run_causal_target_pairs_from_records(
        *arguments, targets, PROFILE
    )

    assert payload["shared_baseline_used"] is True
    assert payload["shared_baseline_pair_count"] == 2
    assert payload["shared_baseline_equivalence_verified"] is True
    assert payload["shared_baseline_terminal_event_count"] > 0
    assert len(payload["pairs"]) == 2
    for pair, target in zip(payload["pairs"], targets, strict=True):
        assert pair["shared_baseline_used"] is True
        assert pair["shared_baseline_equivalence_verified"] is True
        assert pair["baseline"]["affected_bag_outcomes"][0][
            "runtime_bag_id"
        ] == target["runtime_bag_id"]
        _assert_compact_h_system_pair(pair)
    first_baseline = payload["pairs"][0]["baseline"]
    second_baseline = payload["pairs"][1]["baseline"]
    for nested_key in (
        "cohort_metrics",
        "raw_bag_cohort_metrics",
        "invariants",
        "replay_hashes",
    ):
        assert first_baseline[nested_key] is not second_baseline[nested_key]


def _assert_compact_h_system_pair(pair: dict[str, object]) -> None:
    assert pair["g4irsf23_plain_baseline_replay"] is True
    assert pair["g4irsf23_compact_h_system_output"] is True
    assert pair["cohort_difference_sidecar"] is None
    assert pair["cohort_difference_sidecar_serialized"] is False
    assert pair["realized_externality"] is None
    assert pair["realized_outcome_deltas"] is None
    for branch_name in ("baseline", "treatment"):
        branch = pair[branch_name]
        assert branch["raw_bag_cohort_metrics"] is not None
        assert branch["raw_bag_sufficient_statistics_sidecar"] is None
        assert branch["raw_bag_sufficient_statistics_serialized"] is False
        assert branch["raw_bag_sufficient_statistics_omission_reason"] == (
            "COMPACT_H_SYSTEM_OUTPUT"
        )
        assert branch["invariants"]["formal_hard_gate_evaluated"] is True
    for field in (
        "system_mean_delta_seconds",
        "system_p95_delta_seconds",
        "system_p99_delta_seconds",
        "deadline_miss_delta",
        "current_bag_cost_seconds",
        "natural_opportunity_seconds",
        "action_change_certificate",
        "hard_gate_pass",
    ):
        assert field in pair
