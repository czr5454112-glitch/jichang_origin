from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_g4irsf4_streaming_jsonl_replay_uses_cpp_continuous_state() -> None:
    from czr005 import cpp_backend
    from scripts.eval.g4i_runtime import (
        _fallback_rules,
        _graph_records,
        _historical_risk_rules,
        _official_mode,
    )

    if not cpp_backend.is_available():
        pytest.skip("C++ backend is not built")

    sample_dir = ROOT / ".pytest_cache" / "czr005"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / "g4irsf4_sample.jsonl"
    source = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"
    sample_path.write_text(
        "\n".join(source.read_text(encoding="utf-8").splitlines()[:12]) + "\n",
        encoding="utf-8",
    )

    policy = json.loads((ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json").read_text(encoding="utf-8"))
    mode = _official_mode()
    node_records, edge_records, heuristic = _graph_records()

    result = cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic,
        task_jsonl_path=sample_path,
        w1=policy["w1"],
        b1=policy["b1"],
        w2=policy["w2"],
        b2=policy["b2"],
        risk_margin_threshold=float(policy.get("risk_margin_threshold", 1.0)),
        risk_historical_threshold=float(policy.get("risk_historical_threshold", 0.5)),
        risk_bottleneck_threshold=float(policy.get("risk_bottleneck_threshold", 5.0)),
        historical_risk_rules=_historical_risk_rules(),
        fallback_rules=_fallback_rules(policy),
        policy_name=mode.policy,
        use_model=mode.use_model,
        rule_only=mode.rule_only,
        risk_gated_rule=mode.risk_gated_rule,
        fallback_name=mode.fallback_name,
        bounded_depth=mode.bounded_depth,
        max_steps=80,
        trace_limit=5,
        summary_only=True,
        profile_enabled=True,
    )

    summary = result["summary"]
    assert summary["runtime_loop_owner"] == "cpp"
    assert summary["continuous_state"] is True
    assert summary["chunk_reset_count"] == 0
    assert summary["python_route_record_list_used"] is False
    assert summary["task_count"] == 12
    assert summary["jsonl_line_count"] == 12
    assert summary["task_order_violations"] == 0
    assert summary["runtime_full_cie_astar_calls"] == 0
    assert summary["node_window_conflicts"] == 0
    assert "failed_reason_counts" in summary
    assert "failed_tasks" in result
