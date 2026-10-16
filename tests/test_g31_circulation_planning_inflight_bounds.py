"""Bounds use source-captured facts; an old empty-transfer ACK supplies none."""
import copy
import math
import pytest
from scripts.experiments.g31_ics_circulation import planning_inflight_bounds as bounds
from scripts.experiments.g31_ics_circulation import public_preexisting_model as model


def fixture():
    contract = model.supported_contract()
    tray = {"tray_id": "E", "business_bag_id": "receiver", "node": 1, "mode": "loaded", "edge_from": 1,
        "edge_to": 3, "reception_node": -1, "generation": 2, "traversal_id": 2, "committed_prefix": [1]}
    capture = {"source_owner": "A", "captured_at": 8.64, "trays": [tray], "known_faults": [],
        "jobs": [{"business_bag_id": "receiver", "status": "in_transit", "origin": 1, "storage_node": -1, "loaded_at": 8.501}]}
    return capture, contract


def test_remote_commitment_cannot_bound_arrival_before_observed_entry():
    c, contract = fixture(); value = bounds.committed_loaded_arrival(c, "E", contract, now=8.67)
    assert value["status"] == "unknown" and value["reason"] == "committed_edge_has_no_observed_entry_bound"
    assert value["native_protection_certified"] is False and value["online_information_delivered"] is False
    assert value["usable_by_stationary_model"] is False


def test_exact_exit_is_only_for_current_source_view_with_same_traversal():
    c, contract = fixture(); view = {"owner_id": "A", "now": 8.67, "trays": copy.deepcopy(c["trays"])}
    view["trays"][0]["edge_exit_at"] = 9.61
    value = bounds.committed_loaded_arrival(c, "E", contract, now=8.67, own_current_view=view)
    assert value["exact_for_observing_source"] and value["earliest_arrival"] == value["latest_arrival"] == 9.61
    view["owner_id"] = "B"
    assert bounds.committed_loaded_arrival(c, "E", contract, now=8.67, own_current_view=view)["status"] == "unknown"


@pytest.mark.parametrize("defect", ("foreign_source", "stale", "bool_identity", "empty_leg", "future_loaded", "receiving_lease", "wrong_prefix", "known_fault", "missing_job"))
def test_uncertain_or_wrong_identity_never_becomes_exact(defect):
    c, contract = fixture(); tray = c["trays"][0]
    if defect == "foreign_source": c["source_owner"] = "B"
    elif defect == "stale": c["captured_at"] = 8.5
    elif defect == "bool_identity": tray["traversal_id"] = True
    elif defect == "empty_leg": tray["mode"] = "empty_transit"
    elif defect == "future_loaded": c["jobs"][0]["loaded_at"] = 9.
    elif defect == "receiving_lease": tray["reception_node"] = 1
    elif defect == "wrong_prefix": tray["committed_prefix"] = [5, 1]
    elif defect == "known_fault": c["known_faults"] = [{"active": True}]
    else: c["jobs"] = []
    assert bounds.committed_loaded_arrival(c, "E", contract, now=8.67)["status"] == "unknown"


def test_old_capture_cannot_assume_current_owner_or_arrival():
    c, contract = fixture(); c["captured_at"] = 9.62
    value = bounds.committed_loaded_arrival(c, "E", contract, now=9.65)
    assert value["status"] == "unknown"
    assert value["usable_by_stationary_model"] is False


def test_no_missing_entry_time_is_invented_from_departed_ack():
    c, contract = fixture(); c["last_delivered_ack"] = {"status": "departed", "observed_at": 3.2, "received_at": -1.}
    a = bounds.committed_loaded_arrival(c, "E", contract, now=8.67)
    c["last_delivered_ack"]["observed_at"] = 999.
    assert bounds.committed_loaded_arrival(c, "E", contract, now=8.67) == a


def test_sequential_native_epoch_is_inside_outward_bound_not_grouped_sum():
    c, contract = fixture(); c["source_owner"] = "B"; c["captured_at"] = 7.659999999999997
    tray = c["trays"][0]; tray.update(node=3, edge_from=3, edge_to=4, traversal_id=3, committed_prefix=[1, 3])
    c["jobs"][0]["loaded_at"] = 5.601
    now = 7.689999999999996
    view = {"owner_id": "B", "now": now, "trays": [{**copy.deepcopy(tray), "edge_exit_at": 7.801}]}
    bound = bounds.committed_loaded_arrival(c, "E", contract, now=now)
    assert bound["status"] == "unknown"
    exact = bounds.committed_loaded_arrival(c, "E", contract, now=now, own_current_view=view)
    assert exact["status"] == "conditional_arrival_enclosure" and exact["earliest_arrival"] == 7.801


def test_reservation_then_later_observed_entry_does_not_use_capture_as_entry_upper_bound():
    c, contract = fixture()
    view = {"owner_id": "A", "now": 8.68, "trays": copy.deepcopy(c["trays"])}
    view["trays"][0]["edge_exit_at"] = 9.67
    # Entry8.67 can be after capture8.64 while remaining on the same committed
    # traversal. Old capture+travel9.64 would wrongly reject this own fact.
    result = bounds.committed_loaded_arrival(c, "E", contract, now=8.68, own_current_view=view)
    assert result["status"] == "conditional_arrival_enclosure" and result["earliest_arrival"] == 9.67
    assert bounds.committed_loaded_arrival(c, "E", contract, now=8.68)["status"] == "unknown"


@pytest.mark.parametrize("exit_at", (None, True, math.nan, 8.67, 9.8))
def test_missing_past_or_impossible_current_receipt_epoch_stays_unknown(exit_at):
    c, contract = fixture(); view = {"owner_id": "A", "now": 8.67, "trays": copy.deepcopy(c["trays"])}
    view["trays"][0]["edge_exit_at"] = exit_at
    assert bounds.committed_loaded_arrival(c, "E", contract, now=8.67, own_current_view=view)["status"] == "unknown"
