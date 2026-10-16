"""Pure proposed-contract tests; none mint native delivery or execution facts."""
from copy import deepcopy
import math
import pytest
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as v3
from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2


def fixture():
    contract = {"node_contracts": [{"node": 0, "resource_owner": "A", "capacity": 2},
        {"node": 1, "resource_owner": "B", "capacity": 2}, {"node": 2, "resource_owner": "A", "capacity": 2}],
        "edge_records": [[0, 1, 2., 2.]], "edge_contracts": [{"from": 0, "to": 1, "capacity": 1}],
        "native_semantics": {"minimum_service_seconds": .001}}
    tray = {"tray_id": "E", "business_bag_id": "", "mode": "empty", "ready_kind": "unknown",
        "node": 0, "edge_from": 0, "edge_to": 1, "reception_node": 1, "generation": 2, "traversal_id": 3,
        "available_at": 0., "service_ready_at": -1., "load_complete_at": -1., "service_ready_known": False,
        "committed_prefix": [0]}
    semantics = dict(queue_discipline="fifo", resource_semantics="receiving", event_semantics="strict",
        scorer_mode="S4_queue_aware_rule_only", merge_grant_rule="M3", merge_grant_timing_mode="jit_fair_aging_deadline",
        minimum_service_seconds=.001)
    bodies = []
    for owner, peer, nodes, trays in (("A", "B", [0, 2], [tray]), ("B", "A", [1], [])):
        local = {"schema": "g31.planning_capture.v1", "message_id": "planning-v3:" + owner,
            "source_owner": owner, "target_owner": peer, "publication_sequence": 1, "captured_at": .5,
            "valid_until": 2., "static_contract_sha256": "a" * 64, "semantics": semantics,
            "jobs": [], "trays": trays, "nodes": [{"node": node, "occupancy": int(node == 1),
                "actual_available": 0, "unrepresented_occupancy": int(node == 1)} for node in nodes], "known_faults": [],
            "coverage": {"scope": "source_waiting_or_locally_carried_released_jobs_and_local_trays",
                "complete_for_declared_local_scope": True, "local_node_ids": nodes, "tray_ids": [t["tray_id"] for t in trays],
                "business_bag_ids": [], "unrepresented_occupancy": int(owner == "B"), "future_arrivals_included": False}}
        base = {"schema": "g31.planning_capture.v2", "local_capture": local, "extension": {
            "schema": "g31.planning_extension.v2", "source_owner": owner, "captured_at": .5,
            "terminal_receipts": [], "submitted_physical_actions": [],
            "completion_coverage": {"scope": "all_source_owned_destination_unload_completions_through_capture",
                "complete_for_declared_scope": True, "through": .5, "source_owned_destination_nodes": nodes,
                "future_events_included": False, "completed_business_bag_ids": []},
            "action_coverage": {"scope": "all_source_submitted_physical_operations_last_delivered_ack", "through": .5,
                "complete_for_declared_scope": True, "includes_unsubmitted_python_plans": False,
                "uses_hidden_execution_truth": False, "submitted_request_ids": [], "unresolved_request_ids": []}}}
        rows = [{"source_owner": owner, "receipt_event": "EDGE_ENTER", "tray_id": "E", "business_bag_id": "",
            "generation": 2, "traversal_id": 3, "edge_from": 0, "edge_to": 1, "entered_at": .25,
            "static_edge_travel_seconds": 1., "derived_edge_exit_at": 1.25}] if trays else []
        bodies.append({"schema": v3.SCHEMA, "capture_v2": base, "extension": {"schema": v3.EXTENSION,
            "source_owner": owner, "captured_at": .5, "source_observed_inflight": rows, "coverage": {
                "scope": v3.SCOPE, "source_owned_inflight_tray_ids": [t["tray_id"] for t in trays],
                "capture_cutoff": .5, "complete_for_declared_source_inflight": True,
                "unmatched_tray_ids": [], "uses_future_event_heap": False}}})
    return bodies, contract


def check(body, contract, **kwargs):
    return v3.validate_inflight(body, contract, **dict(now=.52, delivered_at=.51, **kwargs))


def test_source_observed_entry_is_data_only_and_nested_v2_unchanged():
    bodies, contract = fixture(); before = deepcopy(bodies)
    digest = capture_digest_v2(bodies[0]["capture_v2"])
    result = check(bodies[0], contract)
    assert result["status"] == "conditional_inflight_extension_data"
    assert result["entries"][0]["derived_edge_exit_at"] == 1.25
    assert not result["native_delivery_verified"] and not result["native_protection_certified"]
    assert not result["v2_base_independently_validated"] and not result["current_state_certified"]
    assert len(v3.capture_digest_v3(bodies[0])) == 64
    assert capture_digest_v2(bodies[0]["capture_v2"]) == digest and bodies == before


@pytest.mark.parametrize("field,value", [("generation", 3), ("generation", True), ("traversal_id", 2),
    ("traversal_id", 0), ("edge_to", 2), ("source_owner", "B"), ("receipt_event", "EDGE_EXIT"),
    ("entered_at", .50000001), ("entered_at", float("nan")), ("entered_at", True),
    ("static_edge_travel_seconds", 2.), ("derived_edge_exit_at", 1.2500000000000002),
    ("business_bag_id", "another-job"), ("tray_id", "different")])
def test_rehashed_inconsistent_entry_is_not_usable(field, value):
    bodies, contract = fixture(); bodies[0]["extension"]["source_observed_inflight"][0][field] = value
    # The validator rejects bad facts even if an untrusted caller can rehash them.
    assert check(bodies[0], contract)["status"] == "unknown"


@pytest.mark.parametrize("now,delivered", [(1.25, .51), (1.3, .51), (.6, .51), (.52, .53), (.52, .4), (True, .51)])
def test_arrived_stale_and_undelivered_captures_do_not_become_current(now, delivered):
    bodies, contract = fixture()
    result = v3.validate_inflight(bodies[0], contract, now=now, delivered_at=delivered)
    assert result["status"] == "unknown"


def test_committed_without_matching_actual_entry_remains_unknown():
    bodies, contract = fixture(); extension = bodies[0]["extension"]
    extension["source_observed_inflight"] = []
    extension["coverage"].update(complete_for_declared_source_inflight=False, unmatched_tray_ids=["E"])
    assert check(bodies[0], contract)["reason"] == "unobserved_or_unmatched_committed_entry"
    extension["coverage"].update(complete_for_declared_source_inflight=True, unmatched_tray_ids=[])
    assert check(bodies[0], contract)["status"] == "unknown"


@pytest.mark.parametrize("mutation", ["duplicate", "omitted", "future_heap", "zero_capacity", "extra_field"])
def test_coverage_and_physical_contract_fail_closed(mutation):
    bodies, contract = fixture(); extension = bodies[0]["extension"]
    if mutation == "duplicate": extension["source_observed_inflight"] *= 2
    elif mutation == "omitted": extension["coverage"]["source_owned_inflight_tray_ids"] = []
    elif mutation == "future_heap": extension["coverage"]["uses_future_event_heap"] = True
    elif mutation == "zero_capacity": contract["edge_contracts"][0]["capacity"] = 0
    else: extension["source_observed_inflight"][0]["hidden_event_id"] = 999
    assert check(bodies[0], contract)["status"] == "unknown"


def reconcile(bodies, contract):
    return v3.reconcile_capture_occupancy(bodies, contract, now=.52, delivered_at_by_source={"A": .51, "B": .51})


def test_incoming_reservation_reconciles_once_despite_reception_edge_overlap():
    bodies, contract = fixture(); result = reconcile(bodies, contract)
    assert result["status"] == "conditional_same_timestamp_occupancy_consistency"
    assert result["reservations_by_node"] == {0: [], 1: [["E", 2, 3]], 2: []}
    assert result["captured_at"] == .5 and not result["current_state_certified"]
    assert not result["native_delivery_verified"] and not result["native_protection_certified"]


@pytest.mark.parametrize("mutation", ["missing_owner", "duplicate_owner", "async", "missing_reservation",
    "hidden_unrepresented", "over_capacity", "missing_node", "conflicting_carrier", "different_contract"])
def test_reconciliation_requires_equal_timestamps_and_complete_matched_occupancy(mutation):
    bodies, contract = fixture(); second = bodies[1]["capture_v2"]["local_capture"]
    if mutation == "missing_owner": bodies.pop()
    elif mutation == "duplicate_owner": bodies.append(deepcopy(bodies[0]))
    elif mutation == "async": second["captured_at"] = .49
    elif mutation == "missing_reservation": second["nodes"][0]["occupancy"] = 0
    elif mutation == "hidden_unrepresented": second["nodes"][0]["unrepresented_occupancy"] = 0
    elif mutation == "over_capacity": contract["node_contracts"][1]["capacity"] = 0
    elif mutation == "missing_node": second["nodes"] = []
    elif mutation == "different_contract": second["static_contract_sha256"] = "b" * 64
    else:
        tray = deepcopy(bodies[0]["capture_v2"]["local_capture"]["trays"][0])
        tray.update(node=1, edge_to=-1, edge_from=-1, reception_node=-1, generation=9)
        second["trays"] = [tray]
    assert reconcile(bodies, contract)["status"] == "unknown"


def test_digest_binds_both_unchanged_base_and_new_entry_and_coverage():
    bodies, _ = fixture(); original = v3.capture_digest_v3(bodies[0])
    for mutate in (
        lambda b: b["capture_v2"]["local_capture"].update(publication_sequence=2),
        lambda b: b["extension"]["source_observed_inflight"][0].update(entered_at=.24),
        lambda b: b["extension"]["coverage"].update(unmatched_tray_ids=["E"]),
    ):
        body = deepcopy(bodies[0]); mutate(body)
        assert v3.capture_digest_v3(body) != original


def assert_no_state_certificate(result):
    for flag in ("native_delivery_verified", "native_protection_certified", "v2_base_independently_validated",
                 "current_state_certified", "atomic_capture_cut_verified", "simultaneous_state_certified",
                 "intervening_events_excluded"):
        assert result[flag] is False


def test_equal_timestamp_and_exact_counts_do_not_establish_one_atomic_cut():
    bodies, contract = fixture()
    result = reconcile(bodies, contract)
    assert result["supplied_capture_timestamps_equal"] is True
    assert result["status"] == "conditional_same_timestamp_occupancy_consistency"
    assert_no_state_certificate(result)
    # Different source publication sequence positions are not a global order
    # or barrier. The consistency result cannot upgrade them to simultaneity.
    bodies[0]["capture_v2"]["local_capture"]["publication_sequence"] = 73
    bodies[1]["capture_v2"]["local_capture"]["publication_sequence"] = 2
    different_source_orders = reconcile(bodies, contract)
    assert different_source_orders["reservations_by_node"] == result["reservations_by_node"]
    assert_no_state_certificate(different_source_orders)


def test_nonoccupancy_state_changes_at_same_timestamp_remain_unproved():
    bodies, contract = fixture()
    # An unsubmitted Python plan or an action between the two captures need
    # not change this OR-counted occupancy. This API has no intervening-event
    # trace or synchronization evidence with which to rule out that history.
    baseline = reconcile(bodies, contract)
    bodies[1]["capture_v2"]["extension"]["submitted_physical_actions"] = [{
        "request_id": "unvalidated-later-action-at-same-time"}]
    changed = reconcile(bodies, contract)
    assert changed["status"] == "conditional_same_timestamp_occupancy_consistency"
    assert changed["reservations_by_node"] == baseline["reservations_by_node"]
    assert_no_state_certificate(changed)
    # Nested v2 facts are explicitly not validated by the extension helper;
    # even its matching occupancy must not be a policy admission token.
    assert changed["v2_base_independently_validated"] is False


@pytest.mark.parametrize("claim", ["atomic_capture_cut_verified", "global_event_sequence", "simultaneous_state_certified"])
def test_caller_cannot_add_an_atomic_cut_claim_to_the_extension(claim):
    bodies, contract = fixture(); bodies[0]["extension"][claim] = 123 if claim == "global_event_sequence" else True
    result = check(bodies[0], contract)
    assert result["status"] == "unknown"
    assert_no_state_certificate(result)


def test_unknown_and_single_source_success_keep_every_state_flag_false():
    bodies, contract = fixture()
    assert_no_state_certificate(check(bodies[0], contract))
    bodies.pop()
    result = reconcile(bodies, contract)
    assert result["status"] == "unknown"
    assert_no_state_certificate(result)


@pytest.mark.parametrize("capacity", [True, 1.0, float("nan"), float("inf"), -1, "1"])
def test_invalid_native_edge_capacity_type_cannot_be_consistent(capacity):
    bodies, contract = fixture(); contract["edge_contracts"][0]["capacity"] = capacity
    result = check(bodies[0], contract)
    assert result["status"] == "unknown" and result["reason"] == "invalid_static_edge_contract"
    assert_no_state_certificate(result)


@pytest.mark.parametrize("field,value", [
    ("capacity", True), ("capacity", 2.0), ("capacity", float("nan")),
    ("capacity", float("inf")), ("capacity", 0), ("capacity", -1), ("capacity", "2"),
    ("node", True), ("node", 0.0), ("node", -1), ("node", "0"),
    ("resource_owner", True), ("resource_owner", 1), ("resource_owner", ""),
])
def test_invalid_native_node_contract_cannot_be_consistent(field, value):
    bodies, contract = fixture()
    contract["node_contracts"][0][field] = value
    assert check(bodies[0], contract)["status"] == "unknown"
    assert reconcile(bodies, contract)["status"] == "unknown"


def test_result_flags_and_entries_are_isolated_from_input_and_next_call():
    bodies, contract = fixture(); before = deepcopy(bodies)
    result = check(bodies[0], contract)
    result["atomic_capture_cut_verified"] = True
    result["entries"][0]["entered_at"] = 0.
    assert_no_state_certificate(check(bodies[0], contract))
    assert bodies == before
