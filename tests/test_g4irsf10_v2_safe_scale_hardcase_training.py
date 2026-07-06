from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval import run_g4irsf10_v2_safe_scale_hardcase_training as g10


def test_source_queue_pressure_tracks_backlog_and_delay(tmp_path: Path) -> None:
    path = tmp_path / "queue.jsonl"
    rows = [
        {"task_id": 1, "segment_id": "1:a", "start": 52, "goal": 49, "pass_time": 10.0, "g4irsf7_original_pass_time": 10.2},
        {"task_id": 2, "segment_id": "2:a", "start": 52, "goal": 49, "pass_time": 11.0, "g4irsf7_original_pass_time": 10.3},
        {"task_id": 3, "segment_id": "3:a", "start": 3, "goal": 47, "pass_time": 20.0, "g4irsf7_original_pass_time": 20.9},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    pressure = g10.source_queue_pressure(path)

    assert pressure["source_queue_backlog"] == 2
    assert pressure["max_source_queue_delay"] == 1.0
    assert pressure["total_source_queue_delay"] == 1.0


def test_hard_reasons_capture_tail_fallback_source_pressure() -> None:
    row = {
        "task_id": 7,
        "segment_id": "7:direct",
        "start": 0,
        "goal": 1,
        "attempt_time": 100.0,
        "finish_time": 130.0,
        "goal_reached": True,
        "rule_fallback_calls": 3,
        "wait_seconds": 12.0,
        "source_wait_seconds": 5.0,
        "source_retry_count": 1,
        "loop_count": 1,
        "path": [0, 2, 1],
    }
    reasons = g10._hard_reasons(row, p95=20.0, p99=25.0, heuristic=[[0.0, 1.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 0.0]])

    assert "high_tth_tail" in reasons
    assert "fallback_high_frequency" in reasons
    assert "source_queue_long_backlog" in reasons
    assert "near_loop" in reasons
    assert "edge_pressure_high" in reasons
    assert "large_detour" in reasons


def test_v3_allowed_runtime_features_exclude_forbidden_inputs() -> None:
    features = set(g10.allowed_runtime_features())

    assert features
    assert not (features & set(g10.FORBIDDEN_MODEL_INPUTS))


def test_blocker_row_is_explicit_not_hidden() -> None:
    row = g10.blocker_row("high_flow_no_fault_16x", "16x", "NOT_RUN", "resource boundary")

    assert row["claim_level"] == "blocker_record"
    assert row["task_count"] == ""
    assert "NOT_RUN" in row["note"]
