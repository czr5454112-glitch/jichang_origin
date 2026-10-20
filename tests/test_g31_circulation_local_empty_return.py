"""Native029 gates. Every constructor attempt is journaled; no mocks or airport runs."""
from copy import deepcopy
import json
import os
from pathlib import Path
import time

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation import native028_receiver_fixture as receiver

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "g31.static_node_roles.v1"


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary = str(next((ROOT / "build_lt_session_029_roles/python").glob("czr005_circulation*.pyd")))
    return load_native(binary)


def emit(case, **fields):
    path = os.environ.get("G31_LOCAL_RETURN_GATE_LEDGER")
    if path:
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"case": case, "recorded_at": time.time(), **fields}) + "\n")


def start(native, case, value):
    emit(case, event="native_constructor_attempt", input=value)
    try:
        session = native.NativeSession(value)
    except Exception as error:
        emit(case, event="native_constructor_failed", error=str(error))
        raise
    return session


def finish(case, value, session, horizon=70., requests=()):
    result = session.result_at(horizon)
    replay = deepcopy(value)
    replay["transfers"] = [dict(r, issued_at=r["earliest_departure"]) for r in requests]
    assert audit_result(replay, result)["status"] == "passed"
    emit(case, event="native_result", result=result, state_sha256=session.offline_state_sha256())
    return result


def scene(*, roles=True, local=True, **protocol):
    value = tiny_cycle()
    value["transfers"] = []
    value["owner_protocol"] = dict(enabled=True, timeout=.5, ack_delay=.2, **protocol)
    if local:
        for node in value["node_contracts"]:
            node["zone"] = "A"
            node["resource_owner"] = "A"
    if roles:
        value["static_role_contract"] = dict(schema=SCHEMA, loader_nodes=[0])
    return value


def request(owner="A", **fields):
    return dict(request_id=f"live:1:{owner}:return", owner_id=owner, tray_id="T0", source=4,
                destination=0, earliest_departure=10., expiry=60., message_delay=0.,
                transfer_scope="local_empty_return", **fields)


def test_native_local_return_reloads_identity_ack_checkpoint_and_unique_leg(native):
    case = "local_return_reloads_identity_ack_checkpoint"
    value = scene(drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=1.)
    session = start(native, case, value)
    session.advance_to(10.)
    payload = request()
    assert session.observe_protocol("A")["static_role_contract"] == value["static_role_contract"]
    assert session.submit_protocol_transfer(payload)["status"] == "pending"
    before = session.offline_state_sha256()
    assert session.submit_protocol_transfer(dict(payload, transfer_scope="cross_zone_transfer"))["reason"] == "request_identity_conflict"
    assert session.offline_state_sha256() == before
    assert session.submit_protocol_transfer(dict(payload, request_id="live:1:A:second"))["reason"] == "local_return_tray_already_committed"
    checkpoint = session.checkpoint()
    session.restore(checkpoint)
    assert session.offline_state_sha256() == before == checkpoint.offline_state_sha256
    assert session.observe_protocol("A")["client_transfer_ledger"][0]["transfer_scope"] == "local_empty_return"
    session.advance_to(11.)
    assert session.submit_protocol_transfer(dict(payload, request_id="live:1:A:inflight", earliest_departure=11.))["reason"] == "local_return_tray_not_available"
    assert session.protocol_request("A", payload["request_id"])["status"] == "timeout_unknown"
    assert session.submit_protocol_transfer(payload)["reason"] == "retry_enqueued"
    session.advance_to(11.3)
    assert session.protocol_request("A", payload["request_id"])["status"] == "acknowledged"
    cancel = dict(request_id="live:1:A:cancel", owner_id="A", kind="cancel_transfer",
                  transfer_request_id=payload["request_id"], message_delay=0.)
    assert session.submit_protocol_command(cancel)["status"] == "pending"
    session.advance_to(12.)
    assert session.submit_protocol_command(cancel)["status"] == "pending"
    session.advance_to(12.3)
    assert session.protocol_command("A", cancel["request_id"])["last_delivered_ack"]["status"] == "rejected"
    result = finish(case, value, session, requests=[payload])
    assert [j["status"] for j in result["jobs"]] == ["completed", "completed"]
    assert len(result["transfers"]) == 1
    assert result["transfers"][0]["transfer_scope"] == "local_empty_return"
    assert result["transfers"][0]["status"] == "received"
    assert sum(r["event"] == "EXPORT_GRANTED" for r in result["receipts"]) == 1
    assert sum(r["kind"] == "empty_return" for r in result["leg_identities"]) == 1
    assert result["jobs"][1]["loaded_at"] >= result["transfers"][0]["received_at"]


def test_native_default_same_zone_unknown_scope_and_nonloader_refused(native):
    case = "default_same_zone_unknown_nonloader"
    value = scene()
    session = start(native, case, value)
    session.advance_to(10.)
    base = request()
    unknown = dict(base, request_id="live:1:A:unknown", transfer_scope="unrecognized")
    assert session.submit_protocol_transfer(unknown)["reason"] == "unknown_transfer_scope"
    nonloader = dict(base, request_id="live:1:A:nonloader", destination=5)
    assert session.submit_protocol_transfer(nonloader)["reason"] == "local_return_destination_not_loader"
    assert session.submit_protocol_transfer(dict(base, destination=4))["reason"] == "invalid_transfer"
    base.pop("transfer_scope")
    assert session.submit_protocol_transfer(base)["status"] == "pending"
    result = finish(case, value, session, requests=[base])
    assert result["transfers"][0]["reason"] == "same_zone_transfer_not_authorized"
    assert result["transfers"][0]["transfer_scope"] == "cross_zone_transfer"
    assert not any(x["kind"] == "empty_return" for x in result["leg_identities"])


def test_native_cross_owner_local_refused(native):
    case = "cross_owner_local"
    value = scene()
    value["node_contracts"][0]["resource_owner"] = "B"
    session = start(native, case, value)
    session.advance_to(10.)
    before = session.offline_state_sha256()
    assert session.submit_protocol_transfer(request())["reason"] == "local_return_requires_same_owner"
    assert session.offline_state_sha256() == before
    finish(case, value, session)


def test_native_absent_role_contract_refused(native):
    case = "absent_roles"
    value = scene(roles=False)
    session = start(native, case, value)
    session.advance_to(10.)
    assert session.submit_protocol_transfer(request())["reason"] == "local_return_requires_static_roles"
    finish(case, value, session)


@pytest.mark.parametrize("contract,reason", [
    (dict(schema="g31.static_node_roles.future", loader_nodes=[0]), "unsupported_static_role_contract"),
    (dict(schema=SCHEMA, loader_nodes=[0, 0]), "invalid_loader_role"),
])
def test_native_invalid_static_role_contract_rejected(native, contract, reason):
    value = scene()
    value["static_role_contract"] = contract
    with pytest.raises(ValueError, match=reason):
        start(native, reason, value)


@pytest.mark.parametrize("reserve,full", [(1, False), (0, True)])
def test_native_local_receiver_reserve_and_capacity_still_enforced(native, reserve, full):
    case = "local_receiver_full" if full else "local_receiver_reserve"
    value = receiver.scene(reserve)
    for node in value["node_contracts"]:
        node["zone"] = node["resource_owner"] = "A"
    value["static_role_contract"] = dict(schema=SCHEMA, loader_nodes=[1])
    if full:
        value["trays"].extend([dict(tray_id="P2", node=1), dict(tray_id="P3", node=1)])
    session = start(native, case, value)
    payloads = [dict(r, transfer_scope="local_empty_return") for r in receiver.requests()]
    for payload in payloads:
        assert session.submit_protocol_transfer(payload)["status"] == "pending"
    result = finish(case, value, session, horizon=20., requests=payloads)
    transfers = {r["request_id"]: r for r in result["transfers"]}
    expected = "receiving_full" if full else "receiver_transit_reserve"
    if full:
        assert all(r["reason"] == expected for r in transfers.values())
    else:
        assert transfers[payloads[0]["request_id"]]["status"] == "received"
        assert transfers[payloads[1]["request_id"]]["reason"] == expected


def test_native_original_cross_zone_ack_retry_reception_chain(native):
    case = "cross_zone_original_chain"
    value = scene(roles=False, local=False, drop_ack_packets=1,
                  owner_outages=[dict(owner="A", start=10.2, end=40.)])
    session = start(native, case, value)
    session.advance_to(10.)
    payload = request(owner="B")
    payload.pop("transfer_scope")
    # Explicit local scope never widens a cross-zone request.
    assert session.submit_protocol_transfer(dict(payload, transfer_scope="local_empty_return"))["reason"] == "local_return_requires_same_zone"
    assert session.submit_protocol_transfer(payload)["status"] == "pending"
    session.advance_to(41.)
    assert session.submit_protocol_transfer(payload)["reason"] == "retry_enqueued"
    session.advance_to(41.3)
    assert session.protocol_request("B", payload["request_id"])["status"] == "acknowledged"
    result = finish(case, value, session, requests=[payload])
    assert len(result["transfers"]) == 1 and result["transfers"][0]["received_at"] < 40.
    assert [j["status"] for j in result["jobs"]] == ["completed", "completed"]


def test_native_local_source_min_stock_preserved(native):
    case = "local_source_min_stock"
    value = scene()
    value["node_contracts"][4]["export_min_stock"] = 1
    session = start(native, case, value)
    session.advance_to(10.)
    payload = request()
    assert session.submit_protocol_transfer(payload)["status"] == "pending"
    result = finish(case, value, session, requests=[payload])
    assert result["transfers"][0]["reason"] == "source_module_min_stock"
    assert not any(x["kind"] == "empty_return" for x in result["leg_identities"])
