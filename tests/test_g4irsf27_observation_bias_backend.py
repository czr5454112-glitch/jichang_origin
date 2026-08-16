from __future__ import annotations

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
    return (
        {
            "node_records": nodes,
            "edge_records": edges,
            "heuristic_time": heuristic,
            "bag_records": [
                ("g27-bias", 1, 0.0, 1000.0, 3, 47, "fixture")
            ],
            "event_semantics": "E4",
            "resource_semantics": "R3",
            "enable_source_admission": False,
            "admission_mode": "off",
            "pibt_mode": "P2",
            "priority_mode": "Q0",
            "scorer_mode": "S4",
            "merge_grant_timing_mode": "J2",
            "g4irsf20_event_hotpath_policy": "E2",
        },
        captured,
    )


def test_zero_bias_is_exact_abi_off_and_active_bias_is_append_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fixture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        legacy_observation_bias_max_seconds=0.0,
        legacy_observation_bias_seed=91,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        legacy_observation_bias_max_seconds=3.0,
        legacy_observation_bias_seed=91,
    )

    omitted, explicit_off, active = captured
    assert omitted == explicit_off
    assert active[-3:] == ({}, 3.0, 91)


def test_bias_wrapper_accepts_fixed_seed_and_rejects_negative_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _fixture(monkeypatch)
    for maximum in (1.0, 2.0, 3.0):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            legacy_observation_bias_max_seconds=maximum,
            legacy_observation_bias_seed=20260816,
        )
    assert [row[-2:] for row in captured] == [
        (1.0, 20260816),
        (2.0, 20260816),
        (3.0, 20260816),
    ]

    with pytest.raises(ValueError, match="must be non-negative"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            legacy_observation_bias_max_seconds=-1.0,
        )
    with pytest.raises(ValueError, match="must be non-negative"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            legacy_observation_bias_seed=-1,
        )
