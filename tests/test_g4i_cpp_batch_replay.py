from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_g4i_cpp_batch_replay_runs_episode_without_full_astar() -> None:
    from czr005 import cpp_backend
    from scripts.eval.g4i_runtime import (
        _cpp_replay,
        _g4d_route_records,
        _g4d_windows,
        _official_mode,
        _task_lookup,
        _window_records_from_runtime,
    )

    if not cpp_backend.is_available():
        pytest.skip("C++ backend is not built")

    tasks = _task_lookup()
    windows, _window_map = _g4d_windows()
    window_records = _window_records_from_runtime(windows[:1])
    route_records, _routes = _g4d_route_records(tasks)
    route_records = [row for row in route_records if row[1] == windows[0].name][:12]
    policy = json.loads((ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json").read_text(encoding="utf-8"))

    result = _cpp_replay(
        mode=_official_mode(),
        window_records=window_records,
        route_records=route_records,
        policy_data=policy,
        trace_limit=5,
    )

    assert result["summary"]["runtime_loop_owner"] == "cpp"
    assert result["summary"]["full_cie_astar_runtime_fallback"] is False
    assert result["summary"]["runtime_full_cie_astar_calls"] == 0
    assert result["summary"]["node_window_conflicts"] == 0
    assert result["summary"]["planned_count"] == len(route_records)
    assert len(result["trace"]) > 0
