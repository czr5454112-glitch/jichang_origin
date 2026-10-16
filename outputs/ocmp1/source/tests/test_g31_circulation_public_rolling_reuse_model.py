"""Finite later-state model tests, never native outcome-table proposal inputs."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import public_rolling_reuse_model as rolling
from scripts.experiments.g31_ics_circulation import research_synthetic_reuse_chain as scene


def state(*, phase="first_return", receiver_ready=9.5):
    data = scene.scene(6.)
    contract = rolling.initial.public_contract(data)
    contract["native_semantics"] = copy.deepcopy(rolling.SUPPORTED_NATIVE_SEMANTICS)
    now = 6.91 if phase == "first_return" else 9.26
    jobs = {j["business_bag_id"]: {**copy.deepcopy(j), "status": "waiting_for_tray", "loaded_at": -1.,
        "storage_entered_at": -1., "storage_released_at": -1.} for j in data["jobs"]}
    jobs["receiver"]["status"] = "loading"
    jobs["loaded"]["status"] = "completed"
    jobs["reuse1"]["status"] = "waiting_for_tray" if phase == "first_return" else "in_transit"
    if phase == "first_reuse_route": jobs["reuse1"]["loaded_at"] = 9.22
    trays = {
        "L": {"tray_id": "L", "node": 6 if phase == "first_return" else 7, "mode": "empty" if phase == "first_return" else "loaded",
            "business_bag_id": "" if phase == "first_return" else "reuse1", "edge_from": -1, "edge_to": -1, "reception_node": -1,
            "available_at": 6.9, "generation": 2, "traversal_id": 8, "committed_prefix": [6] if phase == "first_return" else [7],
            "service_ready_known": True, "service_ready_at": 6.9 if phase == "first_return" else 9.32,
            "ready_kind": "empty_available_at" if phase == "first_return" else "committed_local_service_end"},
        "E": {"tray_id": "E", "node": 1, "mode": "loading", "business_bag_id": "receiver", "edge_from": -1, "edge_to": -1,
            "reception_node": -1, "available_at": receiver_ready, "generation": 2, "traversal_id": 1, "committed_prefix": [1],
            "service_ready_known": True, "service_ready_at": receiver_ready,
            "ready_kind": "observed_load_completion", "load_complete_at": receiver_ready}}
    resources = {n[0]: {"node": n[0], "occupancy": sum(t["node"] == n[0] for t in trays.values()),
        "actual_available": sum(t["node"] == n[0] and t["mode"] == "empty" for t in trays.values())} for n in data["node_records"]}
    records = [{"owner": o, "identity": "declared-test-capture:" + o, "captured_at": now - .005,
        "delivered_at": now - .001, "valid_until": now + .1, "known_faults": [], "unrepresented_occupancy": 0,
        "unresolved_tray_request_ids": [], "semantics": copy.deepcopy(rolling.SUPPORTED_NATIVE_SEMANTICS)} for o in ("A", "B")]
    owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
    for record in records:
        record["node_ids"] = [n for n, o in owners.items() if o == record["owner"]]
        record["tray_ids"] = [key for key, tray in trays.items() if owners[tray["node"]] == record["owner"]]
        record["job_ids"] = sorted({tray["business_bag_id"] for key, tray in trays.items() if key in record["tray_ids"] and tray["business_bag_id"]}
            | {key for key, job in jobs.items() if job["status"] == "waiting_for_tray" and owners[job["origin"]] == record["owner"]})
    terminals = [{"business_bag_id": "loaded", "status": "completed", "source_owner": "A", "completed_at": 6.8,
        "captured_at": now - .02, "delivered_at": now - .01, "identity": "declared-test-terminal"}]
    return contract, jobs, trays, resources, {"now": now, "phase": phase, "source_records": records,
        "terminal_receipts": terminals, "owner_pending_tray_requests": []}


def bundle(**kw):
    contract, jobs, trays, resources, args = state(**kw)
    return rolling.assemble_later(contract, jobs, trays, resources, **args)


def test_later_return_projects_real_reuses_and_freezes_completed_prefix():
    b = bundle(); before = copy.deepcopy(b)
    prediction = rolling.predict(b, {"reuse_next": 8, "return_delay": 0.})
    assert prediction["status"] == "conditional_prediction" and set(prediction["completion"]) == rolling.JOBS
    assert prediction["completion"]["loaded"] == 6.8 and b == before
    assert len([r for r in prediction["physical_projection"] if r["event"] == "EMPTY_RECEIVED" and r["tray"] == "L"]) == 2
    assert [c["next"] for c in prediction["later_choices"]] == [8, 3]
    assert not prediction["native_feasibility_certified"] and not prediction["online_information_delivered"]


def test_replanning_at_loaded_reuse_phase_uses_one_remaining_return():
    b = bundle(phase="first_reuse_route")
    prediction = rolling.predict(b, {"reuse_next": 8, "return_delay": .1})
    assert prediction["status"] == "conditional_prediction"
    assert len([r for r in prediction["physical_projection"] if r["event"] == "EMPTY_RECEIVED" and r["tray"] == "L"]) == 1


def test_no_absence_based_terminal_inference_or_unknown_inflight_clearance():
    contract, jobs, trays, resources, args = state(); args["terminal_receipts"] = []
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert "missing_finished_prefix_receipt" in b["reasons"] and rolling.propose(b)["selected_action"] is None
    contract, jobs, trays, resources, args = state(); trays["E"]["edge_to"] = 3
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert "unknown_inflight_or_receiving_clearance" in b["reasons"]


def test_route_message_cannot_be_assumed_to_arrive_after_commit_or_source_capture_expiry():
    contract, jobs, trays, resources, args = state(phase="first_reuse_route")
    trays["L"]["service_ready_at"] = args["now"] + .009
    args["source_records"][0]["valid_until"] = args["now"]
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert "route_window_commits_before_message_or_unknown" in b["reasons"]
    assert "invalid_or_stale_declared_source_capture" in b["reasons"]


def test_resource_uncertainty_and_unsupported_pending_action_fail_closed():
    contract, jobs, trays, resources, args = state()
    next(e for e in contract["edge_contracts"] if (e["from"], e["to"]) == (3, 4))["entry_headway"] = 9.
    args["owner_pending_tray_requests"] = ["old-unresolved"]
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert "unsupported_fixed_contract:edge_contracts" in b["reasons"]
    contract, jobs, trays, resources, args = state(); args["owner_pending_tray_requests"] = ["old-unresolved"]
    assert "unresolved_owned_tray_request" in rolling.assemble_later(contract, jobs, trays, resources, **args)["reasons"]


def test_declared_wrong_owner_coverage_cannot_make_a_supported_state():
    contract, jobs, trays, resources, args = state()
    args["source_records"][0]["tray_ids"] = []
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert "declared_source_authority_or_coverage_mismatch" in b["reasons"]


def test_equal_information_budget_and_all_unexecuted_candidates_retained():
    b = bundle()
    results = [rolling.propose(b, method=m, evaluation_budget=4) for m in ("coordinate_strict", "coordinate_plateau", "resource_pair_repair")]
    assert all(r["evaluations"] == 4 for r in results)
    assert len({r["candidate_denominator"] for r in results}) == 1
    assert all(sum(x["evaluation_status"] == "unknown_unexecuted" for x in r["rows"]) == r["candidate_denominator"] - 4 for r in results)
    assert all(not r["native_protection_certified"] and not r["online_information_delivered"] for r in results)


@pytest.mark.parametrize("field,value", [("message_delay", 1.), ("ack_delay", 1.), ("retry", 9.),
    ("period", .1), ("horizon", 80.), ("expiry", 90.), ("native_dispatch_quantum", .01)])
def test_unsupported_protocol_cannot_reuse_hardcoded_timing(field, value):
    contract, jobs, trays, resources, args = state(); contract["protocol"][field] = value
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert b["status"] == "unknown" and "unsupported_fixed_contract:protocol" in b["reasons"]
    assert rolling.predict(b, {"reuse_next": 8, "return_delay": 0.})["status"] == "unknown_missing_input"


@pytest.mark.parametrize("mutation", ["extra_edge", "outgoing_order", "service", "capacity", "scorer", "min_service", "old_edge_headway"])
def test_exact_fixture_guard_covers_routing_and_all_preexisting_edge_clearances(mutation):
    contract, jobs, trays, resources, args = state()
    if mutation == "extra_edge": contract["edge_records"].append([7, 4, .1, 1.])
    elif mutation == "outgoing_order": contract["node_records"][7][5].reverse()
    elif mutation == "service":
        contract["node_records"][7] = list(contract["node_records"][7]); contract["node_records"][7][2] = 2.
    elif mutation == "capacity": contract["node_contracts"][4]["capacity"] = 1
    elif mutation == "scorer": contract["native_semantics"]["scorer_mode"] = "other"
    elif mutation == "min_service": contract["native_semantics"]["minimum_service_seconds"] = .01
    else: next(e for e in contract["edge_contracts"] if (e["from"], e["to"]) == (1, 3))["entry_headway"] = 50.
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert b["status"] == "unknown" and rolling.propose(b)["selected_action"] is None


@pytest.mark.parametrize("mutation", ["captured_before_empty", "loading_crossed", "loaded_future", "unknown_ready", "remote_pending", "wrong_jobs", "missing_semantics"])
def test_capture_age_alone_does_not_prove_stationarity_or_complete_public_state(mutation):
    contract, jobs, trays, resources, args = state(phase="first_reuse_route" if mutation == "loaded_future" else "first_return")
    if mutation == "captured_before_empty": args["source_records"][0]["captured_at"] = args["now"] - .04
    elif mutation == "loading_crossed": trays["E"]["service_ready_at"] = trays["E"]["load_complete_at"] = args["now"] - .001
    elif mutation == "loaded_future": jobs["reuse1"]["loaded_at"] = args["now"] + .001
    elif mutation == "unknown_ready": trays["E"]["ready_kind"] = "unknown"
    elif mutation == "remote_pending": args["source_records"][1]["unresolved_tray_request_ids"] = ["remote-unresolved"]
    elif mutation == "wrong_jobs": jobs["reuse2"]["load_seconds"] = 100.
    else: args["source_records"][0].pop("semantics")
    assert rolling.assemble_later(contract, jobs, trays, resources, **args)["status"] == "unknown"


def test_nonfinite_or_malformed_contract_is_unknown_not_a_crash_or_empty_success():
    contract, jobs, trays, resources, args = state(); contract["node_records"] = None
    assert rolling.assemble_later(contract, jobs, trays, resources, **args)["status"] == "unknown"


def test_conflicting_terminal_state_or_duplicate_coverage_cannot_be_normalized_away():
    contract, jobs, trays, resources, args = state(); jobs["loaded"]["status"] = "waiting_for_tray"
    assert rolling.assemble_later(contract, jobs, trays, resources, **args)["status"] == "unknown"
    contract, jobs, trays, resources, args = state(); args["source_records"][0]["tray_ids"].append("L")
    b = rolling.assemble_later(contract, jobs, trays, resources, **args)
    assert "duplicate_declared_coverage_identity" in b["reasons"]
    contract, jobs, trays, resources, args = state(); trays["E"]["service_ready_at"] = float("nan")
    assert rolling.assemble_later(contract, jobs, trays, resources, **args)["status"] == "unknown"
