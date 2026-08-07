from __future__ import annotations

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records


def _request(count: int) -> dict[str, object]:
    nodes, edges, heuristic = canonical_graph_records()
    return {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [
            (
                f"g19-progress-{index}",
                80_000 + index,
                float(index) * 0.01,
                10_000.0,
                3,
                47,
                "typed-direct",
            )
            for index in range(count)
        ],
        "summary_only": True,
        "trace_limit": 0,
        "event_trace_limit": 0,
    }


def test_wall_bound_returns_compact_unfinalized_progress() -> None:
    if not cpp_backend.is_available():
        pytest.skip("native extension is not available")
    payload = cpp_backend.g4irsf11_event_runtime_from_records(
        **_request(128),
        bounded_wall_seconds=1.0e-9,
        bounded_check_every_events=1,
    )
    assert payload["execution_status"] == "BOUNDED_PROGRESS"
    assert payload["stop_reason"] == "WALL_LIMIT"
    assert "bags" not in payload
    progress = payload["progress"]
    assert progress["schema"] == "czr005.g4irsf19.runtime_progress.v1"
    assert progress["phase"] == "READY"
    assert progress["requested_bags"] == 128
    assert progress["event_total"] == 0
    # Release events plus a bounded number of runtime-maintenance wakeups.
    assert progress["heap_size"] >= 128
    assert progress["completed_bags"] == 0
    assert progress["failed_bags"] == 0
    assert payload["summary"]["bounded_progress"] is True


def test_unbounded_default_still_finalizes_normally() -> None:
    if not cpp_backend.is_available():
        pytest.skip("native extension is not available")
    payload = cpp_backend.g4irsf11_event_runtime_from_records(
        **_request(1),
    )
    assert "execution_status" not in payload
    assert len(payload["bags"]) == 1
    assert payload["summary"]["completed_count"] == 1
    assert payload["summary"]["failed_count"] == 0
