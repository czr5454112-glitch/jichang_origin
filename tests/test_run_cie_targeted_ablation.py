from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.eval import run_cie_targeted_ablation as runner


def _full_g31_request(binary: Path) -> dict[str, object]:
    return {
        "scenario": "cie_targeted_ablation_map2_2x",
        "node_records": [[0, 0, 0.2], [1, 0, 0.4]],
        "edge_records": [[0, 1, 1.0, 1.0]],
        "heuristic_time": [[0.0, 1.2], [9.0, 0.0]],
        "bag_records": [["0:0", 0, 1, 0.0, 0.0]],
        "scorer_mode": "S4_queue_aware_rule_only",
        "queue_time_scaling": "raw_count_as_seconds",
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "g4irsf20_event_hotpath_policy": "E2",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "complete_on_goal_arrival": True,
        "enable_cie_component_activation": True,
        "max_simulation_time": runner.activation.FIXED_END_EPOCH,
        "max_events": runner.activation.MAX_EVENTS,
        "expected_binary_path": str(binary.resolve()),
    }


def _base_contract() -> dict[str, object]:
    return {
        "static_potential": "H_SA",
        "potential_contract": {
            "mode": "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL"
        },
    }


@pytest.mark.parametrize(("arm", "mask"), list(runner.ARMS.items()))
def test_every_registered_arm_changes_only_the_mask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arm: str,
    mask: int,
) -> None:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"binary")
    original = _full_g31_request(binary)
    rows = ({"task_id": 1, "segment_id": "1:0"},)
    monkeypatch.setattr(
        runner.activation,
        "prepare_runtime_request",
        lambda **_kwargs: (rows, deepcopy(original), _base_contract()),
    )
    monkeypatch.setattr(
        runner,
        "validate_registered_2x_population",
        lambda **_kwargs: None,
    )

    _rows, request, contract = runner.prepare_targeted_request(
        map_name="map2",
        scale=2,
        arm=arm,
        canonical_path=tmp_path / "canonical.jsonl",
        binary=binary,
    )

    assert request["s4_score_component_mask"] == mask
    expected_changes = [] if arm == "FULL_S4" else ["s4_score_component_mask"]
    assert contract["changed_request_fields_from_full_s4"] == expected_changes
    assert contract["identity_pass"] is True
    for key, value in original.items():
        if key != "s4_score_component_mask":
            assert request[key] == value


def test_only_registered_complete_2x_population_is_accepted() -> None:
    with pytest.raises(runner.TargetedAblationError, match="only for the 2x"):
        runner._validate_scale(1)
    runner._validate_scale(2)

    runner.validate_registered_2x_population(
        raw_bag_count=57_012, segment_count=87_206
    )
    with pytest.raises(
        runner.TargetedAblationError, match="not the registered complete 2x"
    ):
        runner.validate_registered_2x_population(
            raw_bag_count=28_506, segment_count=43_603
        )


def test_dry_run_records_native_identity_and_external_activation_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "czr005_cpp.pyd"
    canonical = tmp_path / "map2_2x.jsonl"
    evidence = tmp_path / "activation.json"
    manifest = tmp_path / "manifest.yaml"
    binary.write_bytes(b"binary")
    canonical.write_text("{}\n", encoding="utf-8")
    evidence.write_text('{"status":"ACTIVATED"}\n', encoding="utf-8")
    manifest.write_text("version: 1\n", encoding="utf-8")
    original = _full_g31_request(binary)
    rows = ({"task_id": 1, "segment_id": "1:0"},)
    monkeypatch.setattr(
        runner.activation,
        "prepare_runtime_request",
        lambda **_kwargs: (rows, deepcopy(original), _base_contract()),
    )
    monkeypatch.setattr(
        runner,
        "validate_registered_2x_population",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        runner.cpp_backend,
        "g4irsf11_event_runtime_from_records",
        lambda **_kwargs: pytest.fail("dry-run invoked native execution"),
    )

    result = runner.execute_run(
        map_name="map2",
        scale=2,
        arm="FULL_MINUS_Q",
        canonical_path=canonical,
        binary=binary,
        activation_evidence_path=evidence,
        revision_manifest_path=manifest,
        dry_run=True,
    )

    assert result["status"] == "READY_CIE_TARGETED_ABLATION_DRY_RUN"
    assert result["native_execution_started"] is False
    assert result["algorithm"]["s4_score_component_mask"] == 14
    assert result["algorithm"]["static_potential"] == "H_SA"
    assert result["algorithm"]["coordination_protocol"].startswith("J2_M3")
    assert result["algorithm"]["event_hotpath_policy"] == "E2"
    assert result["selection_protocol"][
        "activation_evidence_interpreted_by_runner"
    ] is False
    assert result["selection_protocol"][
        "arm_selected_from_outcomes_by_runner"
    ] is False
    assert len(result["provenance"]["binary_sha256"]) == 64
    assert len(result["provenance"]["canonical_workload_sha256"]) == 64


def test_execution_forces_two_x_timing_na_and_preserves_activation_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "czr005_cpp.pyd"
    canonical = tmp_path / "nanning_2x.jsonl"
    evidence = tmp_path / "activation.json"
    manifest = tmp_path / "manifest.yaml"
    binary.write_bytes(b"binary")
    canonical.write_text("{}\n", encoding="utf-8")
    evidence.write_text("{}\n", encoding="utf-8")
    manifest.write_text("version: 1\n", encoding="utf-8")
    original = _full_g31_request(binary)
    rows = ({"task_id": 1, "segment_id": "1:0", "goal": 1},)
    monkeypatch.setattr(
        runner.activation,
        "prepare_runtime_request",
        lambda **_kwargs: (rows, deepcopy(original), _base_contract()),
    )
    monkeypatch.setattr(
        runner,
        "validate_registered_2x_population",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(runner, "REGISTERED_2X_RAW_BAG_COUNT", 1)
    monkeypatch.setattr(runner, "REGISTERED_2X_SEGMENT_COUNT", 1)
    monkeypatch.setattr(
        runner.activation,
        "_execution_integrity",
        lambda *_args: {"pass": True, "gates": {"base": True}, "not_measured": []},
    )
    monkeypatch.setattr(
        runner.activation,
        "_mechanism_projection",
        lambda _summary: {"event_count": 9},
    )
    monkeypatch.setattr(
        runner.g26,
        "summarize_paper_outcome",
        lambda *_args, **_kwargs: {
            "success": {
                "primary_completed_raw_bags": {"count": 1, "rate": 1.0},
                "finish_le_std": {"count": 1, "rate": 1.0},
                "finish_le_std_minus_2700_literal": {"count": 0, "rate": 0.0},
            }
        },
    )
    monkeypatch.setattr(
        runner.cie_business,
        "summarize",
        lambda *_args, **_kwargs: {"denominator": 1},
    )
    telemetry = {"Q": {"decision_any_candidate_nonzero_count": 3}}

    result = runner.execute_run(
        map_name="nanning",
        scale=2,
        arm="H_PLUS_Q_PLUS_I",
        canonical_path=canonical,
        binary=binary,
        activation_evidence_path=evidence,
        revision_manifest_path=manifest,
        executor=lambda **_request: {
            "summary": {
                "s4_score_component_mask": 3,
                "cie_component_activation": telemetry,
                "event_count": 9,
                "decision_count": 4,
            },
            "bags": [{"segment_id": "1:0"}],
        },
    )

    assert result["status"] == "COMPLETE"
    assert result["full_population_timing"] == {
        "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
        "raw_bag_count": None,
        "survivor_or_common_cohort_used": False,
        "distributions": None,
    }
    assert result["activation_telemetry"] == telemetry
    assert result["fixed_denominator_business"]["capacity"]["count"] == 1
    assert result["runtime"]["peak_rss_bytes"] == "NOT_MEASURED"
