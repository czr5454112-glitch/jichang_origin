"""LT2 C1: lawful decision identity and real delivered-ACK P5 handoff."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.local_context import (
    LocalContextToken, PROTOCOL_OBSERVATION, protocol_projection)
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.p5_handoff import (
    FACTORS, build_domain, build_legacy_domain, build_protocol_domain,
    scenario_input, submit_protocol_action)
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient


def protocol_view():
    data = scenario_input(FACTORS[0])
    data.update(schema=PROTOCOL_OBSERVATION, owner_id="A", now=.11, known_faults=[],
                client_transfer_ledger=[], client_requests=[], client_commands=[],
                delivered_transfer_acks=[], delivered_command_acks=[])
    data["trays"] = [{"tray_id": f"T{i}", "node": i, "mode": "hold", "edge_to": -1,
                      "available_at": .81, "business_bag_id": f"U{i}",
                      "generation": 1, "traversal_id": 2} for i in range(3)]
    data["jobs"] = [dict(j, status="waiting_for_tray" if j["business_bag_id"] in ("D0", "D1") else "completed",
                         storage_node=j.get("storage_node", -1), storage_release_at=j.get("storage_release_at", 0.),
                         storage_min_dwell=j.get("storage_min_dwell", 0.))
                    for j in data["jobs"] if j["business_bag_id"] != "P"]
    data["delivered_messages"] = [{"kind": "service_forecast", "status": "conditional", "message_id": "public:P:1",
        "source_owner": "C", "target_owner": "A", "tray_id": "TP", "next": 3,
        "observed_at": .05, "delivered_at": .07, "generation": 1, "publication_sequence": 1,
        "entry_estimate": 2.05, "release_estimate": 4.1}]
    return data


def test_protocol_domain_has_context_and_no_truth_version_or_preallocated_request_id():
    view = protocol_view()
    domain = build_domain(view)
    assert domain["status"] == "complete_finite_public_domain"
    assert domain["schema"] == "g31.handoff_protocol_domain.v2"
    for action in domain["actions"]:
        for candidate in action["candidates"]:
            assert "expected_version" not in candidate["request"]
            assert "request_id" not in candidate["request"]
            assert "version" not in candidate["read_set"]
            assert candidate["request"]["decision_context"] == domain["local_context"]
    assert '"version"' not in json.dumps(domain)
    assert '"expected_version"' not in json.dumps(domain)
    assert "unknown_until_native" in domain["executable_status"]


def test_projection_ignores_truth_version_offline_extras_and_remote_dynamic_sensors():
    original = protocol_view()
    poisoned = deepcopy(original)
    poisoned.update(version=987, offline_truth={"remote_unreceived": 2},
                    transfers=[{"tray_id": "T0", "status": "granted", "destination": 3}])
    for node in poisoned["node_contracts"]:
        if node["resource_owner"] != "A":
            node.update(occupancy=555, actual_available=999)
    assert protocol_projection(poisoned) == protocol_projection(original)
    assert LocalContextToken.from_observation(poisoned) == LocalContextToken.from_observation(original)
    for view in (original, poisoned):
        view.pop("transfers", None)
    a, b = build_domain(original), build_domain(poisoned)
    assert a["actions"] == b["actions"]


@pytest.mark.parametrize("field", ["generation", "traversal_id", "mode"])
def test_local_stage_aba_dependencies_change_token_without_changing_static_hash(field):
    a = protocol_view(); b = deepcopy(a)
    b["trays"][0][field] = "empty_available" if field == "mode" else 3
    first, second = LocalContextToken.from_observation(a), LocalContextToken.from_observation(b)
    assert first != second and first.static_contract_sha256 == second.static_contract_sha256


def test_delivered_channel_sequence_and_message_body_both_change_token():
    a = protocol_view(); b = deepcopy(a)
    b["delivered_messages"][0]["publication_sequence"] += 1
    assert LocalContextToken.from_observation(a) != LocalContextToken.from_observation(b)
    b = deepcopy(a); b["delivered_messages"][0]["release_estimate"] += 1
    assert LocalContextToken.from_observation(a) != LocalContextToken.from_observation(b)
    b = deepcopy(a); b["delivered_command_acks"].append({"request_id": "r", "sequence": 1, "delivered_at": .1})
    assert LocalContextToken.from_observation(a) != LocalContextToken.from_observation(b)


def test_static_contract_hash_excludes_local_occupancy_and_includes_geometry():
    a = protocol_view(); b = deepcopy(a); b["node_contracts"][0]["occupancy"] = 1
    assert LocalContextToken.from_observation(a).static_contract_sha256 == LocalContextToken.from_observation(b).static_contract_sha256
    b["edge_records"][0] = (9, 0, .8, 1.)
    assert LocalContextToken.from_observation(a).static_contract_sha256 != LocalContextToken.from_observation(b).static_contract_sha256


def test_missing_remote_contract_returns_unknown_and_needed_message():
    view = protocol_view()
    job = next(j for j in view["jobs"] if j["business_bag_id"] == "D1")
    view["jobs"].remove(job)
    next(n for n in view["node_contracts"] if n["node"] == 4)["resource_owner"] = "B"
    view["delivered_messages"].append({"kind": "demand", "message_id": "B:A:1", "source_owner": "B",
        "target_owner": "A", "observed_at": .05, "delivered_at": .07, "publication_sequence": 1,
        "jobs": [{"business_bag_id": "D1", "origin": 4, "arrival": 0., "deadline": 150., "status": "waiting_for_tray"}]})
    result = build_domain(view)
    assert result["status"] == "unknown_private_service_contract" and not result["actions"]
    requirement, = result["message_requirements"]
    assert requirement["source_owner"] == "B" and requirement["business_bag_id"] == "D1"
    assert requirement["status"] == "required_message_not_available_in_current_native_protocol"


def test_explicit_legacy_entry_is_preserved_and_cannot_accept_protocol_observation():
    online = protocol_view()
    legacy = deepcopy(online); legacy.update(schema="g31.regional_observation.v1", version=6)
    old = build_legacy_domain(legacy)
    assert old["actions"][1]["candidates"][0]["request"]["expected_version"] == 6
    with pytest.raises(ValueError, match="legacy_versioned"):
        build_legacy_domain(online)
    with pytest.raises(ValueError, match="protocol_observation"):
        build_protocol_domain(legacy)


def test_context_has_json_roundtrip_and_is_not_mutated_with_input():
    view = protocol_view(); context = LocalContextToken.from_observation(view)
    saved = context.to_dict(); view["trays"][0]["generation"] += 1
    assert context.to_dict() == saved == json.loads(json.dumps(saved))
    assert LocalContextToken.from_observation(view).identity != context.identity


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        pytest.skip("requires explicitly identified G31_CIRCULATION_BINARY")
    return load_native(binary)


def test_native_hidden_receiver_outage_has_identical_context_until_ack_delivery(native):
    a = tiny_cycle(); a["transfers"] = []
    a["options"]["max_simulation_time"] = 140.
    a["owner_protocol"] = {"enabled": True, "timeout": .5, "ack_delay": 100.}
    b = deepcopy(a); b["owner_protocol"]["owner_outages"] = [{"owner": "A", "start": 9., "end": 20.}]
    sessions = [native.NativeSession(data) for data in (a, b)]
    for session in sessions:
        session.advance_to(10.)
        session.submit_protocol_transfer({"request_id": "live:1:B:future", "owner_id": "B", "tray_id": "T0",
            "source": 4, "destination": 0, "earliest_departure": 50., "expiry": 60., "message_delay": 0.})
        session.advance_to(11.)
    left, right = sessions
    assert left.offline_state_sha256() != right.offline_state_sha256()  # diagnostic assertion only
    assert left.observe_protocol("B") == right.observe_protocol("B")
    assert LocalContextToken.from_observation(left.observe_protocol("B")) == LocalContextToken.from_observation(right.observe_protocol("B"))
    for session in sessions:
        session.advance_to(110.1)
    assert left.observe_protocol("B")["delivered_transfer_acks"]
    assert not right.observe_protocol("B")["delivered_transfer_acks"]
    assert LocalContextToken.from_observation(left.observe_protocol("B")) != LocalContextToken.from_observation(right.observe_protocol("B"))


def test_native_p5_protocol_adapter_submits_without_legacy_endpoint_and_restores_context(native):
    data = scenario_input(FACTORS[0])
    data["owner_protocol"] = {"enabled": True, "timeout": .5, "ack_delay": .02}
    session = native.NativeSession(data); session.advance_to(.11)
    view = session.observe_protocol("A"); domain = build_domain(view)
    assert domain["status"] == "complete_finite_public_domain"
    action = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["joint_handoff"])
    assert action["candidates"]
    client = ProtocolClient(session)
    submitted = submit_protocol_action(client, action, view)
    assert submitted["status"] == "submitted" and not submitted["atomic"]
    assert submitted["physical_resolution"] == "unknown_until_delivered_ack"
    for row in client.state["outbox"].values():
        assert "expected_version" not in row["payload"]
        assert row["payload"]["decision_context"] == domain["local_context"]
    checkpoint = session.checkpoint()
    restored = native.NativeSession(data); restored.restore(checkpoint)
    saved = json.loads(json.dumps(client.state))
    clone = ProtocolClient(restored, state=saved)
    assert LocalContextToken.from_observation(restored.observe_protocol("A")) == LocalContextToken.from_observation(session.observe_protocol("A"))
    for runner in (client, clone):
        runner.session.advance_to(20.); runner.refresh(retry=True)
        runner.session.advance_to(21.); runner.refresh(retry=False)
    assert session.offline_state_sha256() == restored.offline_state_sha256()
    assert client.state == clone.state
    assert all(row.get("client_view", {}).get("last_delivered_ack") for row in client.state["outbox"].values())


def test_native_adapter_rejects_changed_context_before_any_submission(native):
    data = scenario_input(FACTORS[0]); data["owner_protocol"] = {"enabled": True}
    session = native.NativeSession(data); session.advance_to(.11)
    view = session.observe_protocol("A"); domain = build_domain(view)
    action = next(a for a in domain["actions"] if a["candidates"])
    session.advance_to(.12)
    client = ProtocolClient(session)
    result = submit_protocol_action(client, action, view)
    assert result["status"] == "unknown_changed_local_context" and not client.state["outbox"]
