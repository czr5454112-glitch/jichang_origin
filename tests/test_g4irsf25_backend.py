from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records


def _fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], list[tuple[object, ...]]]:
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
        "bag_records": [("g25", 1, 0.0, 1000.0, 3, 47, "fixture")],
        "event_semantics": "E4",
        "resource_semantics": "R3",
        "enable_source_admission": False,
        "admission_mode": "off",
        "pibt_mode": "P2",
        "priority_mode": "Q0",
        "scorer_mode": "S4",
        "merge_grant_timing_mode": "J2",
        "g4irsf20_event_hotpath_policy": "E2",
    }
    return common, captured


def _arm() -> dict[str, object]:
    return {
        "branch_node": 6,
        "first_edge": 8,
        "rejoin_node": 13,
        "corridor_nodes": [6, 8, 11, 13],
        "support": 32,
        "training_support": 16,
        "static_duration_seconds": 12.0,
        "system_intercept": -1.0,
        "private_intercept": 0.5,
    }


def _artifact(mode: str = "observe") -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf25.clcr.v1",
        "mode": mode,
        "feature_names": list(cpp_backend.G4IRSF25_CLCR_FEATURE_NAMES),
        "record_trajectories": True,
        "trajectory_max_seconds": 600.0,
        "min_support": 8,
        "margin_seconds": 0.5,
        "private_cap_seconds": 60.0,
        "t0_metric": "target_queue_plus_incoming",
        "arms": [_arm()],
        "training_metadata": {"split": "chronological"},
    }


def test_empty_clcr_keeps_existing_abi_and_active_appends_g24_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fixture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    artifact = _artifact()
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf25_clcr_artifact=artifact,
    )

    baseline, active = captured
    assert active[-3] == "E2"
    assert active[-2] == {}
    assert active[-1] == artifact
    assert len(active) == len(baseline) + 2


def test_explicit_off_clcr_keeps_existing_abi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fixture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf25_clcr_artifact={
            "schema": "czr005.g4irsf25.clcr.v1",
            "mode": "off",
        },
    )
    assert captured[1] == captured[0]


def test_clcr_path_and_mapping_are_equivalent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    common, captured = _fixture(monkeypatch)
    artifact = _artifact()
    path = tmp_path / "clcr.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf25_clcr_artifact=artifact,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf25_clcr_artifact=path,
    )
    assert captured[0][-1] == captured[1][-1]


def test_clcr_rejects_wrong_features_unknown_keys_and_non_s4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, _captured = _fixture(monkeypatch)
    wrong_features = _artifact()
    wrong_features["feature_names"] = list(
        reversed(cpp_backend.G4IRSF25_CLCR_FEATURE_NAMES)
    )
    with pytest.raises(ValueError, match="21-feature order"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf25_clcr_artifact=wrong_features,
        )
    unknown = {**_artifact(), "future_route": [6, 13]}
    with pytest.raises(ValueError, match="unknown keys"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf25_clcr_artifact=unknown,
        )
    with pytest.raises(ValueError, match="requires the frozen S4"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **{**common, "scorer_mode": "S3"},
            g4irsf25_clcr_artifact=_artifact(),
        )


def test_clcr_and_g24_dlp_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, _captured = _fixture(monkeypatch)
    dlp = {
        "schema": "czr005.g4irsf24.dlp.v1",
        "mode": "ewma",
        "beta": 1.0,
        "min_support": 8,
        "margin_seconds": 0.5,
        "detour_allowance_seconds": 2.0,
        "edge_residuals": [],
        "value_residuals": [],
    }
    with pytest.raises(ValueError, match="cannot be active together"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf24_dlp_artifact=dlp,
            g4irsf25_clcr_artifact=_artifact(),
        )
