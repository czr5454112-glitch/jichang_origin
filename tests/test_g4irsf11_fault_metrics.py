from __future__ import annotations

import math

from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics


def test_temporal_fault_requires_physical_repair_and_delayed_message() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    bags = [
        {"release_time": 0.0, "finish_time": 5.0, "completed": True},
        {"release_time": 12.0, "finish_time": 22.0, "completed": True},
    ]
    events = [
        {"event": "FAULT", "time": 10.0, "from_node": 0, "to_node": 1, "reason": "physical_state_change"},
        {"event": "FAULT", "time": 12.0, "from_node": 0, "to_node": 1, "reason": "local_message_delivery"},
        {"event": "REPAIR", "time": 20.0, "from_node": 0, "to_node": 1, "reason": "physical_state_change"},
        {"event": "REPAIR", "time": 22.0, "from_node": 0, "to_node": 1, "reason": "local_message_delivery"},
    ]

    row = fault_window_metrics(bags, events, {}, [window], max_recovery_seconds=5.0)[0]

    assert row["physical_fault_event_count"] == 1
    assert row["physical_repair_event_count"] == 1
    assert row["message_delivery_event_count"] == 2
    assert row["fault_edge_traversal_count"] == 0
    assert row["recovery_time_seconds"] == 2.0
    assert row["fault_recovery_pass"] is True


def test_static_removal_or_fault_traversal_cannot_pass() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0)
    bags = [{"release_time": 12.0, "finish_time": -1.0, "completed": False}]
    events = [
        {"event": "EDGE_ENTER", "time": 15.0, "from_node": 0, "to_node": 1},
    ]

    row = fault_window_metrics(bags, events, {}, [window], max_recovery_seconds=5.0)[0]

    assert row["physical_fault_event_count"] == 0
    assert row["physical_repair_event_count"] == 0
    assert row["fault_edge_traversal_count"] == 1
    assert math.isinf(row["recovery_time_seconds"])
    assert row["fault_recovery_pass"] is False
