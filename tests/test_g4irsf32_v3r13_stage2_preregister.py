from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf32_v3r13_stage2_preregister as prereg


@pytest.fixture(scope="module")
def artifact() -> dict[str, object]:
    return prereg.build_preregistration()


def test_outcome_blind_populations_are_the_frozen_cross_map_closures(
    artifact: dict[str, object],
) -> None:
    assert artifact["pass"] is True
    selection = artifact["selection"]
    assert selection["candidate_outcomes_consulted"] is False
    assert selection["candidate_execution_started"] is False
    assert selection["native_runtime_executed"] is False
    assert selection["anchor_window"] == {
        "start_inclusive": 19_200.0,
        "end_exclusive": 19_800.0,
    }
    assert selection["registered_paired_arms"] == ["off", "closed_loop"]

    populations = artifact["populations"]
    expected = {"1x": (540, 998, 147, 42), "2x": (877, 1_599, 147, 71)}
    for scale, (raw, segments, external, local) in expected.items():
        row = populations[scale]
        assert row["raw_task_count"] == raw
        assert row["segment_count"] == segments
        assert len(row["anchor_task_ids"]) == raw
        assert len(row["ordered_segment_ids"]) == segments
        assert row["nanning_target_composition"] == {
            "external_start_53": external,
            "local_start_49": local,
        }
        assert row["checks"]["task_ids_match_between_maps"] is True
        assert row["checks"]["anchor_segment_ids_match_between_maps"] is True
        assert row["checks"]["ordered_segment_ids_match_between_maps"] is True


def test_control_only_routes_and_map2_structure_freeze_the_fault_roles(
    artifact: dict[str, object],
) -> None:
    populations = artifact["populations"]
    for scale in ("1x", "2x"):
        route = populations[scale]["static_g31_off_route"]
        assert route["candidate_outcomes_consulted"] is False
        assert route["edge_traversal_counts"]["50->25"] > 0
        assert route["edge_traversal_counts"]["100->102"] == 0
        assert route["pass"] is True

    map2 = artifact["map2_structural_negative_control"]
    assert map2["mixed_origin_source_nodes"] == []
    assert set(map2["source_indegrees"].values()) == {0}
    assert map2["checks"] == {
        "all_source_indegrees_zero": True,
        "registered_fault_edge_present": True,
    }


def test_exact_ten_semantic_cases_and_registered_edges(
    artifact: dict[str, object],
) -> None:
    cases = artifact["cases"]
    assert len(cases) == 10
    by_id = {row["case_id"]: row for row in cases}
    assert len(by_id) == 10
    for scale in (1, 2):
        active = by_id[
            f"g4irsf32_s2_nanning_{scale}x_fault_source_chain_active_single_1"
        ]
        inactive = by_id[
            f"g4irsf32_s2_nanning_{scale}x_fault_source_chain_inactive_single_8"
        ]
        sentinel = by_id[
            f"g4irsf32_s2_map2_{scale}x_fault_sentinel_single_1"
        ]
        assert active["fault_edges"] == [[50, 25]]
        assert inactive["fault_edges"] == [[100, 102]]
        assert sentinel["fault_edges"] == [[6, 12]]


def test_writer_creates_only_one_new_json_and_refuses_overwrite(
    artifact: dict[str, object], tmp_path: Path
) -> None:
    output = tmp_path / "registered.json"
    prereg.write_preregistration(artifact, output)
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == prereg.STATUS
    assert list(tmp_path.iterdir()) == [output]
    with pytest.raises(FileExistsError):
        prereg.write_preregistration(artifact, output)
