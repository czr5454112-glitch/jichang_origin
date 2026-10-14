"""Conditional messages use local starts; their delivery cannot refresh hidden state."""
from copy import deepcopy
import os
from pathlib import Path
import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def fixture():
    data = tiny_cycle()
    data["transfers"] = []
    # A real ownership boundary on the first edge, keeping topology unchanged.
    data["node_contracts"][1]["resource_owner"] = "B"
    return data


def test_service_forecast_delay_snapshot_checkpoint_and_owner_visibility(native):
    data = fixture()
    source = native.NativeSession(data)
    assert source.publish_service_forecast("A", "B", "T0", 1, .4)["status"] == "rejected"
    source.advance_to(.05)
    assert source.publish_service_forecast("A", "B", "T0", 1, .4)["status"] == "pending"
    assert source.observe("B")["delivered_messages"] == []
    branch = source.fork()
    branch.advance_to(.45)
    assert source.observe("B")["delivered_messages"] == []
    messages = branch.observe("B")["delivered_messages"]
    assert len(messages) == 1
    message = messages[0]
    assert message["kind"] == "service_forecast" and message["status"] == "conditional"
    assert message["estimate_scope"] == "next_node_service_completion"
    assert message["observed_at"] == .05 and message["delivered_at"] == .45
    assert message["entry_estimate"] == pytest.approx(.15)
    assert message["release_estimate"] == pytest.approx(1.2)
    assert message["generation"] == 1 and message["traversal_id"] == 0
    assert message["business_bag_id"] == "B1" and message["tray_id"] == "T0"
    assert branch.observe("A")["delivered_messages"] == []
    assert branch.publish_service_forecast("A", "B", "T0", 1, 0)["status"] == "rejected"
    source.advance_to(.45)
    assert source.observe("B") == branch.observe("B")
    assert source.offline_state_sha256() == branch.offline_state_sha256()
    branch.advance_to(3)
    assert branch.observe("B")["delivered_messages"][0] == message
    message["entry_estimate"] = -100
    assert branch.observe("B")["delivered_messages"][0]["entry_estimate"] == pytest.approx(.15)


def test_forecast_and_transfer_api_responses_ignore_private_future(native):
    first = fixture()
    first["jobs"][1]["arrival"] = 30
    second = deepcopy(first)
    second["jobs"][1]["arrival"] = 40
    second["faults"] = [{"from": 1, "to": 2, "start": 35, "end": 45}]
    hidden = dict(request_id="guess-future", tray_id="T0", source=0, destination=4,
                  issued_at=40, message_delay=0, earliest_departure=40, expiry=60)
    second["transfers"].append(hidden)
    a, b = native.NativeSession(first), native.NativeSession(second)
    for s in (a, b):
        s.advance_to(.05)
        assert s.cancel_transfer_intent("guess-future", "A") == dict(status="rejected", reason="unknown_request")
        assert s.submit_transfer_intent(dict(hidden, owner_id="A")) == dict(
            status="rejected", reason="online_request_namespace_required")
        assert s.publish_service_forecast("A", "B", "T0", 1, .4)["status"] == "pending"
        s.advance_to(.45)
    for owner in ("A", "B"):
        assert a.observe(owner) == b.observe(owner)
    assert a.offline_state_sha256() != b.offline_state_sha256()
    invalid = fixture()
    invalid["transfers"].append(dict(hidden, request_id="live:reserved"))
    with pytest.raises(ValueError, match="reserved_live_request_namespace"):
        native.NativeSession(invalid)


@pytest.mark.parametrize("source,target,next_node,reason", [
    ("B", "B", 1, "tray_not_visible_to_owner"),
    ("A", "A", 1, "target_owner_mismatch"),
    ("A", "B", 4, "not_a_directed_edge"),
])
def test_service_forecast_rejections_do_not_mutate_native_state(native, source, target, next_node, reason):
    session = native.NativeSession(fixture())
    session.advance_to(.05)
    before = session.offline_state_sha256()
    assert session.publish_service_forecast(source, target, "T0", next_node, .1) == dict(status="rejected", reason=reason)
    assert session.offline_state_sha256() == before


def test_message_ids_do_not_disclose_unrelated_owner_publications(native):
    data = fixture()
    data["node_contracts"][5]["resource_owner"] = "C"
    a, b = native.NativeSession(data), native.NativeSession(data)
    for s in (a, b):
        s.advance_to(.05)
    b.publish_demand("C", "C", 0)
    b.advance_to(.05)
    assert a.observe("B") == b.observe("B")
    for s in (a, b):
        s.publish_service_forecast("A", "B", "T0", 1, .4)
        s.publish_demand("A", "B", .4)
        s.advance_to(.45)
    assert a.observe("B") == b.observe("B")
    # The channel counters themselves survive restoring after actual messages.
    restored = a.fork()
    assert restored.publish_demand("A", "B", 0) == a.publish_demand("A", "B", 0)
    restored.advance_to(.45)
    a.advance_to(.45)
    assert restored.observe("B") == a.observe("B")


def test_private_traversals_do_not_change_local_versions_or_route_authorization(native):
    from scripts.experiments.g31_ics_circulation.probe_private_traversal_counter import inputs
    first, second = inputs()
    for data in (first, second):
        data["jobs"][0]["allow_suffix_reroute"] = True
    a, b = native.NativeSession(first), native.NativeSession(second)
    for s in (a, b):
        s.advance_to(1.2)
    assert a.observe("A") == b.observe("A")
    internal = [s.offline_diagnostics()["trays"][0]["internal_traversal_id"] for s in (a, b)]
    assert internal == [1, 2]  # Offline identity remains globally unique.
    for s in (a, b):
        s.advance_to(2.17)
        tray = next(t for t in s.observe("A")["trays"] if t["tray_id"] == "T0")
        assert tray["node"] == 1 and tray["edge_to"] == -1
        request = dict(request_id="local-version-route", owner_id="A", business_bag_id="B1", tray_id="T0",
                       expected_generation=tray["generation"], expected_traversal=tray["traversal_id"],
                       expiry=10, message_delay=0, **{"from": 1, "next": 2})
        assert s.submit_route_intent(request)["status"] == "pending"
        s.advance_to(2.17)
        assert s.observe("A")["route_requests"][-1]["status"] == "updated"
    assert a.observe("A") == b.observe("A")


def test_delayed_withdrawal_is_idempotent_can_arrive_first_and_does_not_cancel_physics(native):
    data = fixture()
    s = native.NativeSession(data)
    s.advance_to(.05)
    published = s.publish_service_forecast("A", "B", "T0", 1, 2)
    original_id = published["message_id"]
    before = s.offline_state_sha256()
    assert s.withdraw_service_forecast("B", original_id, 0) == dict(status="rejected", reason="unknown_owned_forecast")
    assert s.offline_state_sha256() == before
    # The publisher retains permission over its soft forecast after tray motion.
    s.advance_to(.5)
    assert s.withdraw_service_forecast("A", original_id, .1)["status"] == "pending"
    before_duplicate = s.offline_state_sha256()
    assert s.withdraw_service_forecast("A", original_id, .1) == dict(status="duplicate", reason="withdrawal_pending")
    assert s.offline_state_sha256() == before_duplicate
    branch = s.fork()
    s.advance_to(.6)
    tombstone = s.observe("B")["delivered_messages"][0]
    assert tombstone["kind"] == "service_forecast" and tombstone["status"] == "withdrawn"
    assert tombstone["supersedes"] == original_id and tombstone["publication_sequence"] == 2
    assert tombstone["observed_at"] == .5 and tombstone["delivered_at"] == .6
    assert s.withdraw_service_forecast("A", original_id, 1) == dict(status="duplicate", reason="withdrawal_delivered")
    assert branch.observe("B")["delivered_messages"] == []
    for runtime in (s, branch):
        runtime.advance_to(2.05)
        messages = runtime.observe("B")["delivered_messages"]
        assert len(messages) == 2
        conditional = next(m for m in messages if m["status"] == "conditional")
        assert conditional["message_id"] == original_id and conditional["publication_sequence"] == 1
        assert conditional["observed_at"] == .05 and conditional["entry_estimate"] == pytest.approx(.15)
    assert s.observe("B") == branch.observe("B")
    assert s.offline_state_sha256() == branch.offline_state_sha256()
    # Withdrawal neither unloads nor erases the original real service.
    assert s.result_at(30)["jobs"][0]["status"] == "completed"


def test_offline_diagnostics_are_copies_and_not_online_features(native):
    s = native.NativeSession(fixture())
    s.advance_to(.11)
    before = s.offline_state_sha256()
    diagnostics = s.offline_diagnostics()
    assert diagnostics["schema"] == "g31.circulation.offline_diagnostics.v1"
    assert diagnostics["trays"][0]["active_leg"] == 0
    assert diagnostics["legs"][0]["runtime_id"] == 0
    assert "resource_waits" not in s.observe("A") and "junctions" not in s.observe("A")
    diagnostics["trays"][0]["active_leg"] = -1
    diagnostics["junctions"].clear()
    assert s.offline_state_sha256() == before
    assert s.offline_diagnostics()["trays"][0]["active_leg"] == 0


def test_only_latest_delivered_demand_snapshot_survives_out_of_order_delivery(native):
    s = native.NativeSession(fixture())
    s.advance_to(.05)
    s.publish_demand("A", "B", 2)
    s.advance_to(.25)
    s.publish_demand("A", "B", 1)
    s.publish_demand("A", "B", 0)
    s.advance_to(.25)
    current = s.observe("B")["delivered_messages"]
    assert len(current) == 1 and current[0]["publication_sequence"] == 3
    assert [j["business_bag_id"] for j in current[0]["jobs"]] == ["B2"]
    branch = s.fork()
    for target in (1.25, 2.05):
        s.advance_to(target)
        branch.advance_to(target)
        assert s.observe("B")["delivered_messages"] == current
        assert s.observe("B") == branch.observe("B")
        assert s.offline_state_sha256() == branch.offline_state_sha256()
