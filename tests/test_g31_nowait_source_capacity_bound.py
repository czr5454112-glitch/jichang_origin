import pytest

from scripts.experiments.g31_no_wait.source_capacity_bound import fifo_recurrence, single_egress_bound, static_costs


def test_release_gaps_fifo_and_finish_not_last_entry():
    assert fifo_recurrence([0, 0, 9000000, 9000000]) == [0, 2000000, 9000000, 11000000]


def test_stable_raw_release_order_and_goal_service_exclusion():
    profile = {"nodes": [{"location": 53, "service_time": 0}, {"location": 49, "service_time": 2},
                         {"location": 10, "service_time": 2}],
               "edges": [{"start": 53, "end": 49, "length": 2}, {"start": 49, "end": 10, "length": 2}]}
    assert static_costs(profile, 10)[53] == 4000000
    rows = [dict(segment_id=str(i), task_id=i, start=53, goal=10, leg="storage_out", pass_time=r)
            for i, r in enumerate((.9, .1, .1))]
    result = single_egress_bound(rows, profile, horizon=7)
    assert [r["segment_id"] for r in result["first_five"]] == ["1", "2", "0"]
    assert [r["earliest_edge_entry_tick"] for r in result["first_five"]] == [1000000, 3000000, 5000000]
    assert result["cannot_finish_by_horizon_lower_bound"] == 1
    assert result["all_outbound_delivered_time_lower_bound_seconds"] == 9


def test_multiple_egress_cannot_be_called_single_channel():
    profile = {"nodes": [{"location": 53, "service_time": 0}, {"location": 49, "service_time": 2},
                         {"location": 50, "service_time": 2}],
               "edges": [{"start": 53, "end": 49, "length": 2}, {"start": 53, "end": 50, "length": 2}]}
    with pytest.raises(ValueError, match="exactly one outgoing"):
        single_egress_bound([], profile)
