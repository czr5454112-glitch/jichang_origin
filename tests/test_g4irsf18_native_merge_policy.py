from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records
from scripts.eval import run_g4irsf18_system_campaign as system_campaign


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/models/g4irsf18_j7_teacher_cf_affine.json"


def _fake_common(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, object], list[tuple[object, ...]]]:
    captured: list[tuple[object, ...]] = []

    def fake_runtime(*args: object) -> dict[str, object]:
        captured.append(args)
        return {"summary": {}}

    fake_module = SimpleNamespace(
        __file__=str(Path(__file__).resolve()),
        g4irsf11_event_runtime_from_records=fake_runtime,
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda search_path=None: fake_module,
    )
    nodes, edges, heuristic = canonical_graph_records()
    common: dict[str, object] = {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [
            ("g18-tail", 1, 0.0, 1000.0, 3, 47, "typed-direct")
        ],
        "event_semantics": "E4",
        "resource_semantics": "R3",
        "enable_source_admission": False,
        "admission_mode": "off",
        "pibt_mode": "P2",
        "priority_mode": "Q0",
        "scorer_mode": "S1",
        "merge_grant_timing_mode": "J2",
    }
    return common, captured


def test_wrapper_materializes_g18_append_only_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fake_common(monkeypatch)
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf18_merge_policy_mode="research_closed_loop",
        g4irsf18_merge_policy_artifact=artifact,
        g4irsf18_merge_research_closed_loop_authorized=True,
        g4irsf18_merge_fixed_research_workload=True,
        g4irsf18_merge_coverage_cap=0.05,
        g4irsf18_merge_max_overrides_per_segment=2,
    )
    assert len(captured) == 1
    args = captured[0]
    assert len(args) == 80
    assert args[-10:] == (
        "jit_fair_aging_deadline",
        "research_closed_loop",
        artifact,
        True,
        True,
        False,
        False,
        0.05,
        2,
        False,
    )


def test_wrapper_materializes_complete_g19_bounded_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fake_common(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        bounded_wall_seconds=0.01,
        bounded_check_every_events=7,
    )
    args = captured[0]
    assert len(args) == 82
    assert args[-12:] == (
        "jit_fair_aging_deadline",
        "off",
        {},
        False,
        False,
        False,
        False,
        0.05,
        2,
        False,
        0.01,
        7,
    )


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"bounded_wall_seconds": 0.0}, ValueError),
        ({"bounded_wall_seconds": float("inf")}, ValueError),
        ({"bounded_check_every_events": 0}, ValueError),
        ({"bounded_check_every_events": True}, TypeError),
    ],
)
def test_wrapper_rejects_invalid_g19_bounds(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    error: type[Exception],
) -> None:
    common, _captured = _fake_common(monkeypatch)
    with pytest.raises(error):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            **kwargs,
        )


def test_research_arm_is_explicit_fixed_workload_and_never_production() -> None:
    arm, note = system_campaign.load_learned_arm(
        ROOT / "artifacts/manifests/g4irsf18_j7_native_research_arm.json"
    )
    assert arm is not None
    assert note == {
        "arm_id": "J7_TEACHER_CF_AFFINE_RESEARCH_5PCT",
        "reason": "INCLUDED_RESEARCH_ONLY",
    }
    assert arm.research_closed_loop_authorized is True
    assert arm.production_closed_loop_authorized is False
    assert arm.timing_mode == "jit_fair_aging_deadline"
    assert arm.native_controls == {
        "g4irsf18_merge_coverage_cap": 0.05,
        "g4irsf18_merge_fixed_research_workload": True,
        "g4irsf18_merge_kill_switch": False,
        "g4irsf18_merge_max_overrides_per_segment": 2,
        "g4irsf18_merge_offline_gate_passed": False,
        "g4irsf18_merge_policy_artifact": (
            "artifacts/models/g4irsf18_j7_teacher_cf_affine.json"
        ),
        "g4irsf18_merge_policy_mode": "research_closed_loop",
        "g4irsf18_merge_production_closed_loop_authorized": False,
        "g4irsf18_merge_research_closed_loop_authorized": True,
    }


def test_wrapper_allows_semantic_invalid_artifact_for_native_j2_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fake_common(monkeypatch)
    invalid_artifact = {"schema": "wrong"}
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf18_merge_policy_mode="shadow",
        g4irsf18_merge_policy_artifact=invalid_artifact,
    )
    assert captured[0][-8] == invalid_artifact


def test_wrapper_rejects_wrong_hook_and_off_mode_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, _captured = _fake_common(monkeypatch)
    wrong_timing = dict(common)
    wrong_timing["merge_grant_timing_mode"] = "J1"
    with pytest.raises(ValueError, match="requires E4"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **wrong_timing,
            g4irsf18_merge_policy_mode="shadow",
            g4irsf18_merge_policy_artifact={"schema": "wrong"},
        )
    with pytest.raises(ValueError, match="runtime controls require"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf18_merge_kill_switch=True,
        )


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("g4irsf18_merge_coverage_cap", 1.1, ValueError),
        ("g4irsf18_merge_coverage_cap", True, TypeError),
        ("g4irsf18_merge_max_overrides_per_segment", -1, ValueError),
        ("g4irsf18_merge_max_overrides_per_segment", True, TypeError),
        ("g4irsf18_merge_kill_switch", 1, TypeError),
    ],
)
def test_wrapper_validates_runtime_control_types(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: object,
    error: type[Exception],
) -> None:
    common, _captured = _fake_common(monkeypatch)
    kwargs = {
        **common,
        "g4irsf18_merge_policy_mode": "shadow",
        "g4irsf18_merge_policy_artifact": {"schema": "wrong"},
        name: value,
    }
    with pytest.raises(error):
        cpp_backend.g4irsf11_event_runtime_from_records(**kwargs)
