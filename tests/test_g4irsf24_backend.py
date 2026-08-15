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
        "bag_records": [("g24", 1, 0.0, 1000.0, 3, 47, "fixture")],
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


def _artifact() -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf24.dlp.v1",
        "mode": "ewma",
        "beta": 1.0,
        "min_support": 8,
        "margin_seconds": 0.5,
        "detour_allowance_seconds": 2.0,
        "edge_residuals": [
            {"from": 3, "to": 4, "residual_seconds": -1.0, "support": 8}
        ],
        "value_residuals": [],
    }


def test_empty_dlp_keeps_existing_abi_and_active_appends_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fixture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf24_dlp_artifact=_artifact(),
    )

    baseline, active = captured
    assert active[-2] == "E2"
    assert active[-1] == _artifact()
    assert len(active) == 84
    assert len(active) == len(baseline) + 1


def test_explicit_off_dlp_keeps_existing_abi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fixture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf24_dlp_artifact={
            "schema": "czr005.g4irsf24.dlp.v1",
            "mode": "off",
        },
    )

    baseline, explicit_off = captured
    assert explicit_off == baseline


def test_dlp_path_and_mapping_are_equivalent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    common, captured = _fixture(monkeypatch)
    path = tmp_path / "dlp.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf24_dlp_artifact=_artifact(),
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf24_dlp_artifact=path,
    )
    assert captured[0][-1] == captured[1][-1]


def test_dlp_requires_schema_mode_and_s4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, _captured = _fixture(monkeypatch)
    with pytest.raises(ValueError, match="schema"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf24_dlp_artifact={"schema": "wrong", "mode": "ewma"},
        )
    with pytest.raises(ValueError, match="requires the frozen S4"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **{**common, "scorer_mode": "S3"},
            g4irsf24_dlp_artifact=_artifact(),
        )
