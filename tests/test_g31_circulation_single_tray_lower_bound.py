"""Independent contract counterexamples for the narrow offline FIFO bound."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation.single_tray_lower_bound import (
    check_actual, fifo_travel_bound,
)


def contract():
    # The tempting direct shortcut is closed. Huge node service is deliberately
    # omitted from the lower bound, while mandatory Storage, hold and reuse stay.
    edges = [(0, 1, 2., 1.), (1, 2, 3., 1.), (2, 0, 4., 1.), (0, 2, .1, 1.)]
    return {
        "node_records": [(n, 1, 100., n, 0, []) for n in range(3)],
        "node_contracts": [{"node": n, "capacity": 1} for n in range(3)],
        "edge_records": edges,
        "edge_contracts": [{"from": u, "to": v, "capacity": 0 if (u, v) == (0, 2) else 1}
                           for u, v, _, _ in edges],
        "trays": [{"tray_id": "T", "node": 0}],
        "jobs": [
            {"business_bag_id": "A", "arrival": 0., "origin": 0, "destination": 2,
             "deadline": 14., "storage_node": 1, "storage_release_at": 10.,
             "storage_min_dwell": 5., "load_seconds": 1., "unload_seconds": 2., "hold_seconds": 3.},
            {"business_bag_id": "B", "arrival": 4., "origin": 0, "destination": 2,
             "deadline": 30., "load_seconds": 1., "unload_seconds": 1., "hold_seconds": 0.},
        ],
        "options": {"queue_discipline": "fifo"},
    }


def test_storage_absolute_release_and_dwell_overlap_and_physical_reuse_is_mandatory():
    result = fifo_travel_bound(contract(), 100.)
    a, b = result["rows"]
    assert a["storage_entry_lower_bound"] == 3.
    # Absolute release 10 overlaps dwell [3, 8]; adding them would be invalid.
    assert a["storage_release_lower_bound"] == 10.
    assert a["completion_lower_bound"] == 15.
    assert a["next_loader_ready_lower_bound"] == 22.  # unload15 + hold3 + return4
    assert b["load_start_lower_bound"] == 22.
    assert b["completion_lower_bound"] == 29.  # closed direct shortcut excluded
    assert b["positive_capacity_directed_paths"]["loaded_direct"] == [0, 1, 2]
    assert result["restricted_sojourn_lower_bound"] == 40.
    assert result["minimum_deadline_misses"] == 1


def test_restriction_at_horizon_keeps_both_jobs_and_unfinished_time():
    result = fifo_travel_bound(contract(), 20.)
    assert result["offered"] == 2
    assert result["restricted_sojourn_lower_bound"] == 31.  # 15 + (20 - 4)


def test_reverse_edge_cannot_be_invented_to_make_empty_return_possible():
    data = contract()
    data["edge_records"] = [e for e in data["edge_records"] if e[:2] != (2, 0)]
    with pytest.raises(ValueError, match="no_positive_capacity_directed_path:2:0"):
        fifo_travel_bound(data, 100.)


@pytest.mark.parametrize("change,reason", [
    ("second_tray", "requires_one_tray"),
    ("second_origin", "requires_one_fifo_origin"),
    ("same_time_arrival", "simultaneous_arrivals"),
    ("non_fifo", "non_fifo_contract"),
])
def test_declines_populations_where_the_sequence_proof_does_not_apply(change, reason):
    data = contract()
    if change == "second_tray":
        data["trays"].append({"tray_id": "T2", "node": 0})
    elif change == "second_origin":
        data["jobs"][1]["origin"] = 1
    elif change == "same_time_arrival":
        data["jobs"][1]["arrival"] = 0.
    else:
        data["options"]["queue_discipline"] = "priority"
    with pytest.raises(ValueError, match=reason):
        fifo_travel_bound(data, 100.)


def actual():
    return {"receipts": [{"event": "LOAD_START", "business_bag_id": b, "tray_id": "T"} for b in ("A", "B")],
            "jobs": [{"business_bag_id": "A", "completed_at": 17., "status": "completed"},
                     {"business_bag_id": "B", "completed_at": 34., "status": "completed"}]}


def test_actual_full_population_gap_and_sequence_are_checked():
    data = contract()
    bound = fifo_travel_bound(data, 100.)
    result = check_actual(bound, actual(), data)
    assert result["metrics"]["offered"] == 2
    assert result["restricted_sojourn_gap_to_lower_bound"] == 7.
    assert result["actual_deadline_misses"] == 2
    wrong_order = actual()
    wrong_order["receipts"].reverse()
    with pytest.raises(ValueError, match="actual_loading_sequence"):
        check_actual(bound, wrong_order, data)


def test_any_bound_exceeding_actual_completion_is_rejected():
    data = contract()
    bound = fifo_travel_bound(data, 100.)
    result = copy.deepcopy(actual())
    result["jobs"][1]["completed_at"] = 28.
    with pytest.raises(ValueError, match="bound_exceeds_actual_completion"):
        check_actual(bound, result, data)
