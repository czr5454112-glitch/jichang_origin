"""Pure fixtures test guards; no forged data can authenticate native delivery."""
import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import public_preexisting_model as model
from scripts.experiments.g31_ics_circulation import native_preexisting_initial_adapter as initial_adapter
from scripts.experiments.g31_ics_circulation import native_preexisting_rolling_adapter as later_adapter
from test_g31_circulation_public_rolling_reuse_model import state as old_later_state


def initial_pair(owner="A", case_index=4):
    case = model.domain.cases()[case_index]; data = model.domain.make_bundle(case)["contract"]
    ownership = {n["node"]: n["resource_owner"] for n in data["node_contracts"]}
    jobs = {j["business_bag_id"]: {**copy.deepcopy(j), "protected_service": True,
        "status": "loading" if j["business_bag_id"] in ("loaded", "blocker") else "waiting_for_tray",
        "loaded_at": -1., "storage_entered_at": -1., "storage_released_at": -1.} for j in data["jobs"]}
    trays = []
    for name, node, bag, finish in (("L", 0, "loaded", .1), ("E", 5, "", 0.), ("P", 1, "blocker", case["blocker_load"])):
        trays.append({"tray_id": name, "node": node, "mode": "loading" if bag else "empty", "business_bag_id": bag,
            "edge_from": -1, "edge_to": -1, "reception_node": -1, "generation": 1, "traversal_id": 0,
            "available_at": finish, "service_ready_at": finish, "service_ready_known": True,
            "ready_kind": "observed_load_completion" if bag else "empty_available_at", "load_complete_at": finish if bag else -1.,
            "committed_prefix": [node]})
    resources = {n: {"node": n, "occupancy": sum(t["node"] == n for t in trays), "actual_available": int(n == 5), "unrepresented_occupancy": 0} for n in ownership}
    envelopes = {}
    for source in ("A", "B"):
        body = {"schema": "g31.planning_capture.v1", "message_id": "fixture:" + source, "source_owner": source,
            "target_owner": ({"A", "B"} - {source}).pop(), "publication_sequence": 1, "captured_at": .06,
            "valid_until": .21, "static_contract_sha256": "a" * 64, "semantics": copy.deepcopy(model.SUPPORTED_NATIVE_SEMANTICS),
            "jobs": [copy.deepcopy(j) for j in jobs.values() if ownership[j["origin"]] == source],
            "trays": [copy.deepcopy(t) for t in trays if ownership[t["node"]] == source],
            "nodes": [r for n, r in resources.items() if ownership[n] == source], "known_faults": []}
        body["coverage"] = {"scope": "source_waiting_or_locally_carried_released_jobs_and_local_trays", "complete_for_declared_local_scope": True,
            "local_node_ids": sorted(r["node"] for r in body["nodes"]), "tray_ids": [t["tray_id"] for t in body["trays"]],
            "business_bag_ids": [j["business_bag_id"] for j in body["jobs"]], "unrepresented_occupancy": 0, "future_arrivals_included": False}
        envelopes[source] = {"schema": "g31.planning_snapshot.v1", "kind": "planning_snapshot", "capture": body,
            "payload_sha256": initial_adapter.capture_digest(body), "digest_format": "g31.planning_capture_digest.v1", "delivered_at": .07, "status": "conditional"}
    own = envelopes[owner]["capture"]
    view = {**copy.deepcopy(data), "owner_id": owner, "now": .11, "known_faults": [], "jobs": copy.deepcopy(own["jobs"]), "trays": copy.deepcopy(own["trays"])}
    for row in view["jobs"]:
        if row["business_bag_id"] == "loaded": row.update(status="in_transit", loaded_at=.1)
    for tray in view["trays"]:
        if tray["tray_id"] == "L": tray.update(mode="loaded", available_at=0.)
    view["node_contracts"] = [{**n, **({k: resources[n["node"]][k] for k in ("occupancy", "actual_available")} if ownership[n["node"]] == owner else {})} for n in view["node_contracts"]]
    ack = {"status": "delivered", "executed_at": .06, "completed_at": .07, "delivered_at": .09,
        "result_id": own["message_id"], "planning_snapshot": envelopes[owner]}
    return view, ack, [envelopes[({"A", "B"} - {owner}).pop()]]


@pytest.mark.parametrize("case_index", range(6))
def test_complete_initial_native_shaped_pair_and_case_derived_from_facts(case_index):
    a = initial_adapter.validate_pair(*initial_pair("A", case_index)); b = initial_adapter.validate_pair(*initial_pair("B", case_index))
    assert a["status"] == b["status"] == "conditional_validated_data", (a, b)
    assert a["bundle"] == b["bundle"]
    assert a["bundle"]["case_from_delivered_contracts"] == model.domain.cases()[case_index]
    assert not a["native_delivery_verified"] and not a["bundle"]["online_information_delivered"]


@pytest.mark.parametrize("defect", ("missing_P", "forged_P_owner", "future_P_ready", "P_unrepresented", "new_capacity", "new_delay", "missing_peer", "expired", "lost_self"))
def test_initial_contract_and_delivery_guards(defect):
    view, ack, peer = initial_pair("B"); message = peer[0]; body = message["capture"]
    p = next(t for t in body["trays"] if t["tray_id"] == "P")
    if defect == "missing_P": body["trays"].remove(p); body["coverage"]["tray_ids"].remove("P")
    elif defect == "forged_P_owner": p["node"] = 7
    elif defect == "future_P_ready": p["service_ready_at"] = p["load_complete_at"] = 999.
    elif defect == "P_unrepresented": body["coverage"]["unrepresented_occupancy"] = 1
    elif defect == "new_capacity": view["node_contracts"][1]["capacity"] = 2
    elif defect == "new_delay": body["captured_at"] = .01
    elif defect == "missing_peer": peer = []
    elif defect == "expired": message["status"] = "expired"
    elif defect == "lost_self": ack["status"] = "pending_delivery"
    message["payload_sha256"] = initial_adapter.capture_digest(body)
    result = initial_adapter.validate_pair(view, ack, peer)
    assert result["status"] == "unknown" and result["native_delivery_verified"] is False


def test_initial_search_budget_and_fixed_family_all_four_times():
    receipt = initial_adapter.validate_pair(*initial_pair()); bundle = receipt["bundle"]
    selected = model.propose_initial(bundle, "coordinate_plateau")
    assert selected["evaluations"] <= 32 and selected["candidate_denominator"] == 32
    for index, time in enumerate(model.domain.domain(model.domain.cases()[4])["public_derivation"]["supply_windows"]):
        row = model.propose_initial(bundle, "finite_horizon_enumeration", fixed_window=index)
        assert row["candidate_denominator"] == 4
        assert row["selected_action"]["initial_next"] == 1 and row["selected_action"]["departure"] == time
        assert set(row["selected_prediction"]["completion"]) == model.JOBS


def later_state():
    _, jobs, trays, _, args = old_later_state()
    case = model.domain.cases()[4]; declared = model.domain.make_bundle(case)["jobs"]
    for name in jobs: jobs[name].update({field: declared[name][field] for field in model.CONTRACT_FIELDS})
    jobs["blocker"] = {**declared["blocker"], "status": "completed", "loaded_at": -1., "storage_entered_at": -1., "storage_released_at": -1.}
    trays["P"] = {"tray_id": "P", "node": 9, "mode": "empty", "business_bag_id": "", "edge_from": -1, "edge_to": -1,
        "reception_node": -1, "available_at": 4.4, "generation": 2, "traversal_id": 1, "committed_prefix": [9],
        "service_ready_known": True, "service_ready_at": 4.4, "ready_kind": "empty_available_at", "load_complete_at": -1.}
    contract = model.supported_contract(); owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
    resources = {n: {"node": n, "occupancy": sum(t["node"] == n for t in trays.values()), "actual_available": sum(t["node"] == n and t["mode"] == "empty" for t in trays.values())} for n in owners}
    for record in args["source_records"]:
        source = record["owner"]
        record["node_ids"] = [n for n, o in owners.items() if o == source]
        record["tray_ids"] = [key for key, t in trays.items() if owners[t["node"]] == source]
    args["terminal_receipts"].append({"business_bag_id": "blocker", "status": "completed", "source_owner": "A", "completed_at": 4.3,
        "captured_at": args["now"] - .02, "delivered_at": args["now"] - .01, "identity": "fixture-blocker-complete"})
    return contract, jobs, trays, resources, args


def test_later_model_keeps_blocker_receipt_and_physical_tray():
    c, j, t, r, kw = later_state(); bundle = model.assemble_later(c, j, t, r, **kw)
    assert bundle["status"] == "conditional_model_input", bundle
    result = model.predict(bundle, {"reuse_next": 8, "return_delay": 0.})
    assert result["status"] == "conditional_prediction" and set(result["completion"]) == model.JOBS
    assert result["completion"]["blocker"] == 4.3
    assert len(bundle["trays"]) == 3 and not bundle["online_information_delivered"]


@pytest.mark.parametrize("defect", ("missing_P_receipt", "P_not_parked", "E_inflight", "pending_action", "changed_protocol", "changed_load", "age"))
def test_later_unsupported_state_never_relaxes_old_guards(defect):
    c, j, t, r, kw = later_state()
    if defect == "missing_P_receipt": kw["terminal_receipts"].pop()
    elif defect == "P_not_parked": t["P"]["mode"] = "hold"
    elif defect == "E_inflight": t["E"]["edge_to"] = 3
    elif defect == "pending_action": kw["source_records"][0]["unresolved_tray_request_ids"] = ["pending"]
    elif defect == "changed_protocol": c["protocol"]["message_delay"] = 1.
    elif defect == "changed_load": j["receiver"]["load_seconds"] = 9.
    elif defect == "age": kw["source_records"][0]["captured_at"] -= .1
    assert model.assemble_later(c, j, t, r, **kw)["status"] == "unknown"


def test_fake_module_never_authenticates_or_creates_session_bound_ledger():
    assert initial_adapter.collect_native(SimpleNamespace(), SimpleNamespace(), "A", "fake")["native_delivery_verified"] is False
    result, ledger = later_adapter.collect_initial_ledger(SimpleNamespace(), SimpleNamespace(), "A", "fake")
    assert ledger is None and result["native_delivery_verified"] is False


def later_pair():
    """Extend native-shaped source envelopes with P; never authenticate them."""
    from test_g31_circulation_native_rolling_adapter import pair as two_tray_pair
    from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2
    view, ack, peer, kwargs = two_tray_pair()
    contract, jobs, trays, resources, args = later_state()
    for job in jobs.values(): job["protected_service"] = True
    kwargs["retained"]["contracts"] = {key: {field: row[field] for field in later_adapter.CONTRACT_FIELDS} for key, row in jobs.items()}
    own = ack["planning_snapshot_v2"]["capture"]; other = peer[0]["capture"]
    for body in (own, other):
        local = body["local_capture"]
        local["jobs"] = [{**kwargs["retained"]["contracts"][j["business_bag_id"]],
            **{f: j[f] for f in ("status", "loaded_at", "storage_entered_at", "storage_released_at")}} for j in local["jobs"]]
    own["local_capture"]["trays"].append(copy.deepcopy(trays["P"]))
    own["local_capture"]["nodes"].append({**resources[9], "unrepresented_occupancy": 0})
    own["local_capture"]["coverage"]["tray_ids"].append("P")
    own["local_capture"]["coverage"]["local_node_ids"].append(9)
    extension = own["extension"]
    extension["completion_coverage"]["source_owned_destination_nodes"] = sorted(set(extension["completion_coverage"]["source_owned_destination_nodes"]) | {9})
    extension["terminal_receipts"].insert(0, {"receipt_id": "completion:1:A:1", "source_local_sequence": 1,
        "source_owner": "A", "event": "UNLOAD_COMPLETE", "status": "completed", "business_bag_id": "blocker",
        "destination": 9, "tray_id": "P", "completed_at": 4.3})
    extension["terminal_receipts"][1].update(receipt_id="completion:1:A:2", source_local_sequence=2)
    extension["completion_coverage"]["completed_business_bag_ids"] = ["blocker", "loaded"]
    view.update({k: copy.deepcopy(contract[k]) for k in ("node_records", "edge_records", "node_contracts", "edge_contracts")})
    owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
    for row in view["node_contracts"]:
        if owners[row["node"]] == "A": row.update({field: resources[row["node"]][field] for field in ("occupancy", "actual_available")})
    view["jobs"] = copy.deepcopy(own["local_capture"]["jobs"])
    view["trays"] = copy.deepcopy(own["local_capture"]["trays"])
    ack["planning_snapshot_v2"]["payload_sha256"] = capture_digest_v2(own)
    peer[0]["payload_sha256"] = capture_digest_v2(other)
    return view, ack, peer, kwargs


def test_three_tray_v2_adapter_retains_both_completed_jobs_without_absence_inference():
    view, ack, peer, kwargs = later_pair()
    result = later_adapter.validate_later_pair(view, ack, peer, **kwargs)
    assert result["status"] == "conditional_validated_later_data", result
    assert result["bundle"]["completed_prefix"] == {"blocker": 4.3, "loaded": 6.8}
    assert set(result["bundle"]["jobs"]) == model.JOBS
    assert result["native_delivery_verified"] is False


@pytest.mark.parametrize("defect", ("missing_P_receipt", "foreign_P_receipt", "future_P_completion", "pending_P_command", "missing_P", "bool_receipt_sequence"))
def test_three_tray_v2_receipt_and_action_coverage_fail_closed(defect):
    from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2
    view, ack, peer, kwargs = later_pair(); body = ack["planning_snapshot_v2"]["capture"]
    extension, local = body["extension"], body["local_capture"]
    if defect == "missing_P_receipt":
        extension["terminal_receipts"].pop(0); extension["terminal_receipts"][0].update(receipt_id="completion:1:A:1", source_local_sequence=1)
        extension["completion_coverage"]["completed_business_bag_ids"] = ["loaded"]
    elif defect == "foreign_P_receipt": extension["terminal_receipts"][0]["source_owner"] = "B"
    elif defect == "future_P_completion": extension["terminal_receipts"][0]["completed_at"] = view["now"] + 1.
    elif defect == "bool_receipt_sequence": extension["terminal_receipts"][0]["source_local_sequence"] = True
    elif defect == "missing_P":
        local["trays"] = [t for t in local["trays"] if t["tray_id"] != "P"]
        local["coverage"]["tray_ids"].remove("P")
        view["trays"] = copy.deepcopy(local["trays"])
    else:
        extension["submitted_physical_actions"] = [{"request_id": "pending-P", "kind": "route", "source_owner": "A", "last_delivered_ack": None}]
        extension["action_coverage"].update(submitted_request_ids=["pending-P"], unresolved_request_ids=["pending-P"])
        kwargs["own_actions"] = [("pending-P", "route")]
    ack["planning_snapshot_v2"]["payload_sha256"] = capture_digest_v2(body)
    result = later_adapter.validate_later_pair(view, ack, peer, **kwargs)
    assert result["status"] == "unknown" and result["native_delivery_verified"] is False


def test_boolean_publication_sequence_is_not_native_integer_identity():
    view, ack, peer = initial_pair("B"); body = peer[0]["capture"]
    body["publication_sequence"] = True; peer[0]["payload_sha256"] = initial_adapter.capture_digest(body)
    result = initial_adapter.validate_pair(view, ack, peer)
    assert result["status"] == "unknown" and result["reasons"] == ["invalid_publication_sequence"]
