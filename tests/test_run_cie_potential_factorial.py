from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import run_cie_potential_factorial as runner


def test_free_flow_excludes_service_while_service_aware_responds() -> None:
    edges = [[0, 1, 1.0, 1.0], [1, 2, 1.0, 1.0], [0, 2, 100.0, 1.0]]
    low_service = [[0, 0, 0.2], [1, 0, 0.3], [2, 0, 0.4]]
    high_service = [[0, 0, 0.2], [1, 0, 7.0], [2, 0, 0.4]]

    ff_low, ff_low_contract = runner.g28.free_flow_potential(low_service, edges)
    ff_high, ff_high_contract = runner.g28.free_flow_potential(high_service, edges)
    sa_low, _ = runner.g28.service_aware_potential(low_service, edges)
    sa_high, _ = runner.g28.service_aware_potential(high_service, edges)

    assert ff_low == ff_high
    assert ff_low[0][2] == pytest.approx(2.0)
    assert ff_low_contract["node_service_time_included"] is False
    assert ff_high_contract["queue_or_calendar_state_included"] is False
    assert sa_low[0][2] != sa_high[0][2]
    assert sa_low[0][2] == pytest.approx(2.5)
    assert sa_high[0][2] == pytest.approx(9.2)


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"factorial-test-binary")
    workload_1x = tmp_path / "one.jsonl"
    workload_2x = tmp_path / "two.jsonl"
    workload_1x.write_text("{}\n", encoding="utf-8")
    workload_2x.write_text("{}\n{}\n", encoding="utf-8")
    values: dict[str, object] = {
        "map": "map2",
        "scale": 1,
        "policy": "s4",
        "potential": "ff",
        "dynamic": "off",
        "service_multiplier": 1.0,
        "release_mode": "canonical",
        "binary": binary,
        "output": tmp_path / "out.json",
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


@pytest.mark.parametrize(
    ("policy", "potential", "dynamic", "scorer", "expected_cell", "mask"),
    [
        ("s4", "ff", "off", "S4", "P0D0", 0),
        ("s4", "sa", "full", "S4", "P1D1", 15),
        (
            "cie_dh",
            "ff",
            "full",
            "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED",
            "CIE_DH_COMMON_EXECUTOR_FREE_FLOW",
            None,
        ),
    ],
)
def test_dry_run_identity_is_explicit_and_does_not_execute_native(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy: str,
    potential: str,
    dynamic: str,
    scorer: str,
    expected_cell: str,
    mask: int | None,
) -> None:
    args = _args(
        tmp_path, policy=policy, potential=potential, dynamic=dynamic
    )
    request = {
        "node_records": [[0, 0, 0.2], [1, 0, 2.0], [2, 0, 0.4]],
        "edge_records": [
            [0, 1, 1.0, 1.0],
            [1, 2, 1.0, 1.0],
            [0, 2, 5.0, 1.0],
        ],
        "heuristic_time": [[0.0, 1.2, 4.2], [9.0, 0.0, 3.0], [9.0, 9.0, 0.0]],
        "minimum_service_seconds": 0.001,
        "scorer_mode": scorer,
        "queue_time_scaling": "raw_count_as_seconds",
        "enable_s4_local_potential_descent_guard": policy == "s4",
        "enable_s4_direct_neighbor_merge_calendar_visibility": policy == "s4",
        "merge_grant_rule": "M1",
        "merge_grant_timing_mode": "jit_fifo",
        "expected_binary_path": str(Path(args.binary).resolve()),
    }
    if policy == "s4":
        request["s4_score_component_mask"] = 15
    workload = SimpleNamespace(
        raw_bag_count=3,
        segment_count=4,
        rows=[],
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
        lambda _args: ("case", workload, request, release),
    )
    monkeypatch.setattr(
        runner.cpp_backend,
        "g4irsf11_event_runtime_from_records",
        lambda **_request: pytest.fail("dry-run invoked the native runtime"),
    )

    result = runner.execute(args)

    assert result["status"] == "READY_CIE_POTENTIAL_FACTORIAL_DRY_RUN"
    assert result["native_execution_started"] is False
    assert result["algorithm"]["cell_id"] == expected_cell
    assert result["algorithm"]["coordination_protocol"] == "neutral_fifo"
    assert result["algorithm"]["s4_score_component_mask"] == mask
    assert result["potential"]["selected_label"] == runner.POTENTIAL_LABELS[potential]
    assert result["potential"]["selection_changes_only_heuristic_time"] is True
    assert result["potential"]["artifacts"]["ff"]["contract"][
        "node_service_time_included"
    ] is False
    assert result["potential"]["artifacts"]["sa"]["contract"][
        "node_service_time_included"
    ] is True
    assert len(result["potential"]["selected_matrix_sha256"]) == 64


def test_service_multiplier_changes_only_physical_node_service_profile() -> None:
    request = {
        "node_records": [[0, 0, 0.2, "a"], [1, 1, 2.0, "b"]],
        "edge_records": [[0, 1, 1.0, 1.0]],
        "tasks": [[0, 1, 2]],
    }

    prepared, contract = runner._apply_service_multiplier(request, 2.0)

    assert prepared["node_records"] == [
        [0, 0, 0.4, "a"],
        [1, 1, 4.0, "b"],
    ]
    assert prepared["edge_records"] is request["edge_records"]
    assert prepared["tasks"] is request["tasks"]
    assert contract["service_time_multiplier"] == 2.0
    assert contract["topology_edges_tasks_release_unchanged"] is True


def test_two_x_paper_timing_is_na_even_when_full_population_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload = SimpleNamespace(raw_bag_count=3, segment_count=3, rows=[])
    monkeypatch.setattr(
        runner.g35,
        "_execution_integrity",
        lambda *_args: {"pass": True},
    )
    monkeypatch.setattr(
        runner.g26,
        "summarize_paper_outcome",
        lambda *_args, **_kwargs: {
            "completed_raw_bag_count": 3,
            "success": {
                "primary_completed_raw_bags": {"count": 3, "rate": 1.0},
                "finish_le_std": {"count": 3, "rate": 1.0},
                "finish_le_std_minus_2700_literal": {"count": 0, "rate": 0.0},
            },
        },
    )
    monkeypatch.setattr(
        runner.g24,
        "timing_distributions",
        lambda *_args: pytest.fail("2x protocol attempted to compute THT"),
    )

    _integrity, subjects = runner._paper_subjects(
        {"completed_count": 3},
        [],
        workload,
        {},
        {"formal_same_hca_release_input": False},
        formal_timing_eligible=False,
    )

    timing = subjects["full_population_raw_bag_timing"]
    assert timing["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
    assert timing["metrics_seconds"] is None


def test_cie_dh_cannot_be_mislabeled_as_dynamic_off(tmp_path: Path) -> None:
    with pytest.raises(runner.PotentialFactorialError, match="not an S4 dynamic"):
        runner.execute(_args(tmp_path, policy="cie_dh", dynamic="off"))
