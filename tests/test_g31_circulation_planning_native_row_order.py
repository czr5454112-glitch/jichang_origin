"""Pure row-order conformance; no native worker or source contract mutation."""
from copy import deepcopy
import pytest

from scripts.experiments.g31_ics_circulation import native_preexisting_rolling_adapter as v2_adapter
from scripts.experiments.g31_ics_circulation import preexisting_v3_data_adapter as v3_adapter
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as v3
from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2
from test_g31_circulation_preexisting_online_model import later_pair
from test_g31_circulation_preexisting_v3_data_adapter import pair
from test_g31_circulation_planning_capture_v3_contract import fixture as extension_fixture, check


@pytest.mark.parametrize("version", [2, 3])
def test_local_job_and_tray_coverage_follows_rows_without_sorting(version):
    view, ack, peer, kwargs = later_pair() if version == 2 else pair("A")
    own = ack["planning_snapshot_v2" if version == 2 else "planning_snapshot_v3"]
    for envelope in (own, peer[0]):
        body = envelope["capture"]
        local = body["local_capture"] if version == 2 else body["capture_v2"]["local_capture"]
        for rows, field, key in (("trays", "tray_ids", "tray_id"), ("jobs", "business_bag_ids", "business_bag_id")):
            local[rows].reverse()
            local["coverage"][field] = [row[key] for row in local[rows]]
        if version == 3:
            entries = {r["tray_id"]: r for r in body["extension"]["source_observed_inflight"]}
            order = [t["tray_id"] for t in local["trays"] if t["edge_to"] >= 0]
            body["extension"]["source_observed_inflight"] = [entries[name] for name in order]
            body["extension"]["coverage"]["source_owned_inflight_tray_ids"] = order
        envelope["payload_sha256"] = (capture_digest_v2 if version == 2 else v3.capture_digest_v3)(body)
    result = (v2_adapter if version == 2 else v3_adapter).validate_later_pair(view, ack, peer, **kwargs)
    expected = "conditional_validated_later_data" if version == 2 else "conditional_validated_later_v3_data"
    assert result["status"] == expected, result
    assert result["native_delivery_verified"] is False


def moving_two():
    bodies, contract = extension_fixture(); body = bodies[0]
    local, extension = body["capture_v2"]["local_capture"], body["extension"]
    original_tray = deepcopy(local["trays"][0]); original_entry = deepcopy(extension["source_observed_inflight"][0])
    local["trays"] = [dict(original_tray, tray_id=name) for name in ("Z-first", "A-second")]
    local["coverage"]["tray_ids"] = ["Z-first", "A-second"]
    extension["source_observed_inflight"] = [dict(original_entry, tray_id=name) for name in ("Z-first", "A-second")]
    extension["coverage"]["source_owned_inflight_tray_ids"] = ["Z-first", "A-second"]
    contract["edge_contracts"][0]["capacity"] = 2
    return body, contract


def test_multiple_observed_entries_follow_input_tray_order_not_id_sort():
    body, contract = moving_two()
    result = check(body, contract)
    assert result["status"] == "conditional_inflight_extension_data"
    assert [r["tray_id"] for r in result["entries"]] == ["Z-first", "A-second"]
    assert not result["native_delivery_verified"] and not result["native_protection_certified"]


@pytest.mark.parametrize("defect", ["coverage_sort", "entry_sort", "duplicate_local", "duplicate_entry", "missing_entry", "unmatched_reverse", "unmatched_original"])
def test_v3_moving_order_identity_and_unmatched_guards_remain_strict(defect):
    body, contract = moving_two(); local = body["capture_v2"]["local_capture"]; extension = body["extension"]
    if defect == "coverage_sort": extension["coverage"]["source_owned_inflight_tray_ids"].sort()
    elif defect == "entry_sort": extension["source_observed_inflight"].sort(key=lambda r:r["tray_id"])
    elif defect == "duplicate_local": local["trays"][1] = deepcopy(local["trays"][0])
    elif defect == "duplicate_entry": extension["source_observed_inflight"][1] = deepcopy(extension["source_observed_inflight"][0])
    elif defect == "missing_entry": extension["source_observed_inflight"].pop()
    else:
        ids = ["Z-first", "A-second"]
        if defect == "unmatched_reverse": ids.reverse()
        extension["coverage"].update(complete_for_declared_source_inflight=False, unmatched_tray_ids=ids)
        extension["source_observed_inflight"] = []
    assert check(body, contract)["status"] == "unknown"


def test_generic_nonascending_node_order_is_explicitly_current_contract_limitation():
    bodies, contract = extension_fixture()
    local = bodies[0]["capture_v2"]["local_capture"]
    local["nodes"].reverse()
    local["coverage"]["local_node_ids"] = [r["node"] for r in local["nodes"]]
    bodies[0]["capture_v2"]["extension"]["completion_coverage"]["source_owned_destination_nodes"] = local["coverage"]["local_node_ids"]
    # Current restricted 3-tray inputs use ascending node rows. This records a
    # broader API's unsupported shape; it does not loosen the frozen contract.
    result = v3.reconcile_capture_occupancy(bodies, contract, now=.52, delivered_at_by_source={"A":.51,"B":.51})
    assert result["status"] == "unknown" and result["reason"] == "incomplete_owned_node_coverage"
