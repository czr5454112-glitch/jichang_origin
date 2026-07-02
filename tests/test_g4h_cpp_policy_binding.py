from __future__ import annotations

import pytest

from czr005 import cpp_backend


def _require_cpp_backend() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def test_g4h_no_astar_policy_decision_uses_local_fallback_without_astar() -> None:
    _require_cpp_backend()

    result = cpp_backend.g4h_no_astar_policy_decision(
        w1=[[0.0], [0.0]],
        b1=[0.0],
        w2=[0.0],
        b2=0.0,
        features=[[0.0, 0.0], [0.0, 0.0]],
        candidates=[17, 21],
        historical_risk=[1.0, 0.0],
        bottleneck_score=[0.0, 0.0],
        risk_margin_threshold=0.02,
        risk_historical_threshold=0.95,
        risk_bottleneck_threshold=99.0,
        fallback_name="node_window_pibt_lite",
        static_cost=[40.0, 42.0],
        wait_seconds=[5.0, 0.0],
        pressure=[1.0, 0.0],
        progress=[2.0, 10.0],
        loop_penalty=[0.0, 0.0],
        backtrack=[0.0, 0.0],
        traffic_penalty=[0.0, 0.0],
        slack_pressure=[0.0, 0.0],
        lookahead_cost=[0.0, 0.0],
        faulted=[False, False],
    )

    assert result["should_fallback"] is True
    assert result["selected_next"] == 21
    assert result["runtime_full_cie_astar_calls"] == 0
