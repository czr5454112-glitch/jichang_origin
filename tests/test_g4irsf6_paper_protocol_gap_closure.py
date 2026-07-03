from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf6_paper_protocol_gap_closure as g6


def test_recompute_heuristic_time_uses_requested_speed() -> None:
    map_data = {
        "nodes": [{"location": 0}, {"location": 1}, {"location": 2}],
        "edges": [
            {"start": 0, "end": 1, "length": 6.0, "speed": 1.0},
            {"start": 1, "end": 2, "length": 4.0, "speed": 1.0},
            {"start": 0, "end": 2, "length": 20.0, "speed": 1.0},
        ],
        "constants": {"edge_speed": 1.0},
    }

    heuristic = g6.recompute_heuristic_time(map_data, speed=2.0)

    assert heuristic[0][2] == 5.0
    assert heuristic[0][1] == 3.0


def test_classify_delay_reason_prioritizes_safety_waits() -> None:
    row = {
        "noastar_tth": 130.0,
        "delta_seconds": 10.0,
        "wait_seconds": 9.0,
        "fallback_calls": 3,
        "loop_count": 0,
        "source_retry": 0,
        "early_bag_split": "False",
    }

    assert g6.classify_delay_reason(row) == "extra_wait_due_to_node_reservation"


def test_strict_winner_allowed_blocks_lower_bound_and_runtime_mismatch() -> None:
    base = {
        "extension_only": False,
        "baseline_level": "executable_runtime",
        "same_input": True,
        "same_metric": True,
        "same_fault_setting": True,
        "same_speed": True,
        "same_time_horizon": True,
        "same_runtime_responsibility": True,
    }

    allowed, _, _ = g6.strict_winner_allowed(base)
    assert allowed is True

    lower_bound = dict(base, baseline_level="lower_bound_only")
    allowed, _, reason = g6.strict_winner_allowed(lower_bound)
    assert allowed is False
    assert "not an executable" in reason

    mismatch = dict(base, same_runtime_responsibility=False)
    allowed, _, reason = g6.strict_winner_allowed(mismatch)
    assert allowed is False
    assert "same-protocol" in reason
