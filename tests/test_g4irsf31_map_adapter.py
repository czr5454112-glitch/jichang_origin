from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from czr005 import cpp_backend
from scripts.eval import g4irsf31_map_adapter as g31


def _synthetic_profile(path: Path) -> Path:
    payload = {
        "name": "five-node-portability-fixture",
        "start_nodes": [0, 1],
        "end_nodes": [4],
        "business_roles": {"storage_source_nodes": [1]},
        "nodes": [
            {
                "location": 0,
                "node_type": 1,
                "service_time": 0.0,
                "x": 0,
                "y": 0,
                "outgoing": [2],
            },
            {
                "location": 1,
                "node_type": 1,
                "service_time": 0.0,
                "x": 1,
                "y": 0,
                "outgoing": [2],
            },
            {
                "location": 2,
                "node_type": 4,
                "service_time": 2.0,
                "x": 2,
                "y": 0,
                "outgoing": [3],
            },
            {
                "location": 3,
                "node_type": 5,
                "service_time": 3.0,
                "x": 3,
                "y": 0,
                "outgoing": [4],
            },
            {
                "location": 4,
                "node_type": 2,
                "service_time": 0.0,
                "x": 4,
                "y": 0,
                "outgoing": [],
            },
        ],
        "edges": [
            {"start": 0, "end": 2, "length": 1.0, "speed": 1.0},
            {"start": 1, "end": 2, "length": 1.0, "speed": 1.0},
            {"start": 2, "end": 3, "length": 1.0, "speed": 1.0},
            {"start": 3, "end": 4, "length": 1.0, "speed": 1.0},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_synthetic_profile_builds_model_free_local_active_request(tmp_path: Path) -> None:
    profile = g31.load_map_profile(_synthetic_profile(tmp_path / "map.json"))
    request, potential = g31.build_s4_request(
        profile,
        [
            {
                "segment_id": "storage-one",
                "task_id": 1,
                "pass_time": 0.0,
                "std": 100.0,
                "start": 1,
                "goal": 4,
            },
            {
                "segment_id": "storage-one-return-leg",
                "task_id": 1,
                "pass_time": 1.0,
                "std": 101.0,
                "start": 0,
                "goal": 4,
            },
        ],
        edge_speed_mps=2.0,
    )

    assert len(request["node_records"]) == 5
    assert {row[3] for row in request["edge_records"]} == {2.0}
    assert request["storage_source_nodes"] == [1]
    assert request["bag_records"][0][-1] == "storage"
    assert [row[1] for row in request["bag_records"]] == [1, 1]
    assert [row[0] for row in request["bag_records"]] == [
        "storage-one",
        "storage-one-return-leg",
    ]
    assert request["queue_discipline"] == "fifo"
    assert request["scorer_mode"] == "S4_queue_aware_rule_only"
    assert (
        request["enable_s4_direct_neighbor_merge_calendar_visibility"]
        is False
    )
    assert request["complete_on_goal_arrival"] is False
    assert request["merge_grant_rule"] == "M3"
    assert request["merge_grant_timing_mode"] == "jit_fair_aging_deadline"
    assert request["g4irsf20_event_hotpath_policy"] == "E2"
    assert request["local_queue_capacity"] == g31.G31_LOCAL_QUEUE_CAPACITY == 0
    assert g31.g14.FROZEN_RUNTIME_CONTROLS["local_queue_capacity"] == 32
    assert "scorer_model_path" not in request
    assert "g4irsf24_dlp_artifact" not in request
    assert request["heuristic_time"][4][4] == 0.0
    assert potential["runtime_full_astar_required"] is False
    assert potential["runtime_decision_complexity"] == "O(outdegree)"

    visible_request, _ = g31.build_s4_request(
        profile,
        [
            {
                "segment_id": "visible",
                "task_id": 2,
                "pass_time": 0.0,
                "std": 100.0,
                "start": 0,
                "goal": 4,
            }
        ],
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    assert (
        visible_request["enable_s4_direct_neighbor_merge_calendar_visibility"]
        is True
    )
    assert visible_request["complete_on_goal_arrival"] is True


def test_map2_profile_keeps_storage_node_52_default() -> None:
    profile = g31.load_map_profile(
        g31.ROOT / "data" / "processed" / "maps" / "map2.json"
    )
    assert profile.storage_source_nodes == (52,)


def test_sparse_node_ids_are_rejected_at_the_actual_heuristic_boundary(
    tmp_path: Path,
) -> None:
    path = _synthetic_profile(tmp_path / "sparse.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["nodes"][-1]["location"] = 7
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(g31.MapProfileError, match="dense zero-based"):
        g31.load_map_profile(path)


def _backend_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], list[tuple[object, ...]]]:
    captured: list[tuple[object, ...]] = []

    def fake_runtime(*args: object) -> dict[str, object]:
        captured.append(args)
        return {"summary": {}}

    module = SimpleNamespace(
        __file__=str(Path(__file__).resolve()),
        g4irsf11_event_runtime_from_records=fake_runtime,
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda search_path=None: module,
    )
    common: dict[str, object] = {
        "node_records": [
            (0, 1, 0.0, 0, 0, [1]),
            (1, 2, 0.0, 1, 0, []),
        ],
        "edge_records": [(0, 1, 1.0, 1.0)],
        "heuristic_time": [[0.0, 1.0], [1.0, 0.0]],
        "bag_records": [("one", 1, 0.0, 10.0, 0, 1, "fixture")],
        "event_semantics": "E4",
        "resource_semantics": "R3",
        "enable_source_admission": False,
        "admission_mode": "off",
        "pibt_mode": "P2",
        "priority_mode": "Q0",
        "scorer_mode": "S4",
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "J2",
        "g4irsf20_event_hotpath_policy": "E2",
    }
    return common, captured


def test_storage_role_tail_is_opt_in_and_legacy_52_call_shape_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _backend_capture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        storage_source_nodes=[52],
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        storage_source_nodes=[0],
    )

    omitted, explicit_default, adapted = captured
    assert omitted == explicit_default
    assert adapted[-4:] == ({}, 0.0, 0, [0])
    assert len(adapted) == len(omitted) + 4


def test_merge_calendar_visibility_is_an_independent_append_only_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _backend_capture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
    )

    omitted, visible, guarded_visible = captured
    assert visible[-6:] == ({}, 0.0, 0, [52], False, True)
    assert guarded_visible[-6:] == ({}, 0.0, 0, [52], True, True)
    assert len(visible) == len(omitted) + 6


def test_goal_arrival_completion_is_final_append_only_default_off_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _backend_capture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        complete_on_goal_arrival=False,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        complete_on_goal_arrival=True,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )

    omitted, explicit_off, active, all_active = captured
    assert omitted == explicit_off
    assert active[-7:] == ({}, 0.0, 0, [52], False, False, True)
    assert all_active[-7:] == ({}, 0.0, 0, [52], True, True, True)
    assert len(active) == len(omitted) + 7


def test_s4_ablation_controls_are_default_compatible_append_only_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _backend_capture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        s4_score_component_mask=15,
        queue_time_scaling="raw_count_as_seconds",
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        s4_score_component_mask=3,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        queue_time_scaling="service_rate_normalized",
    )

    omitted, explicit_defaults, masked, normalized = captured
    assert omitted == explicit_defaults
    assert masked[-8:] == (
        {},
        0.0,
        0,
        [52],
        False,
        False,
        False,
        3,
    )
    assert normalized[-9:] == (
        {},
        0.0,
        0,
        [52],
        False,
        False,
        False,
        15,
        "service_rate_normalized",
    )
    # The active G31 tail also materializes the three intervening
    # G24/observation-bias defaults before the five/six new suffix values.
    assert len(masked) == len(omitted) + 8
    assert len(normalized) == len(omitted) + 9


@pytest.mark.parametrize(
    ("override", "exception", "message"),
    [
        (
            {"s4_score_component_mask": True},
            TypeError,
            "must be an integer, not bool",
        ),
        (
            {"s4_score_component_mask": -1},
            ValueError,
            r"\[0, 15\]",
        ),
        (
            {"s4_score_component_mask": 16},
            ValueError,
            r"\[0, 15\]",
        ),
        (
            {"queue_time_scaling": 1},
            TypeError,
            "must be a string",
        ),
        (
            {"queue_time_scaling": "per_node_tuned"},
            ValueError,
            "raw_count_as_seconds",
        ),
        (
            {"scorer_mode": "S3", "s4_score_component_mask": 1},
            ValueError,
            "require the S4 scorer",
        ),
    ],
)
def test_python_wrapper_validates_s4_ablation_controls(
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, object],
    exception: type[Exception],
    message: str,
) -> None:
    common, _captured = _backend_capture(monkeypatch)
    common.update(override)
    with pytest.raises(exception, match=message):
        cpp_backend.g4irsf11_event_runtime_from_records(**common)


def test_storage_role_tail_rejects_negative_or_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, _captured = _backend_capture(monkeypatch)
    with pytest.raises(ValueError, match="non-negative"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            storage_source_nodes=[-1],
        )
    with pytest.raises(ValueError, match="duplicates"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            storage_source_nodes=[0, 0],
        )
