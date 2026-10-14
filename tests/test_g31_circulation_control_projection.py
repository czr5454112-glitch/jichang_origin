"""Exact public queue representation, not a smaller offered population."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import struct

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import _visible_demand
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def queue_fixture(count=200, trays=1):
    data = tiny_cycle()
    data["transfers"] = []
    job = dict(data["jobs"][0], load_seconds=50, storage_release_at=60)
    data["jobs"] = [dict(job, business_bag_id=f"queue-{i:04d}", arrival=i / 10000)
                    for i in range(count)]
    data["trays"] = [dict(tray_id=f"tray-{i}", node=0) for i in range(trays)]
    data["node_contracts"][0]["capacity"] = max(trays, 1)
    return data


def expected_signature(full):
    rows = sorted([j["business_bag_id"], j["origin"], j["arrival"], j["deadline"]]
                  for j in full["jobs"] if j["status"] in ("waiting", "waiting_for_tray"))
    payload = bytearray(b"g31.demand_signature.v1\n")
    payload += struct.pack(">Q", len(rows))
    for identity, origin, arrival, deadline in rows:
        encoded = identity.encode("utf-8")
        payload += struct.pack(">Q", len(encoded)) + encoded
        payload += struct.pack(">qdd", origin, arrival if arrival else 0.0, deadline if deadline else 0.0)
    return dict(schema="g31.demand_signature.v1", sha256=hashlib.sha256(payload).hexdigest(), waiting_count=len(rows))


def assert_public_projection(session, owner):
    before = session.offline_state_sha256()
    full, compact = session.observe(owner), session.observe_control(owner)
    projection = compact["control_projection"]
    visible = _visible_demand(full)
    waiting = sorted((j for j in visible.values() if j["status"] in ("waiting", "waiting_for_tray")),
                     key=lambda j: (j["arrival"], j["business_bag_id"]))
    assert projection["exact_waiting_count"] == len(waiting)
    assert set(projection["known_origin_nodes"]) == {j["origin"] for j in visible.values()}
    expected_groups = {}
    for global_index, job in enumerate(waiting):
        expected_groups.setdefault(job["origin"], []).append((global_index, job))
    assert {g["origin"] for g in projection["waiting_groups"]} == set(expected_groups)
    for group in projection["waiting_groups"]:
        rows = expected_groups[group["origin"]]
        assert group["count"] == len(rows)
        assert group["demand_observed_at"] == rows[-1][1]["demand_observed_at"]
        heads = group["jobs"]
        assert len(heads) == min(len(rows), group["head_limit"])
        for rank, (head, (global_index, full_job)) in enumerate(zip(heads, rows)):
            assert head["fifo_index"] == rank
            assert head["global_fifo_index"] == global_index
            assert all(head[k] == full_job[k] for k in
                       ("business_bag_id", "origin", "arrival", "deadline", "demand_observed_at"))
    local_ids = {t["business_bag_id"] for t in full["trays"]}
    assert compact["jobs"] == [j for j in full["jobs"] if j["business_bag_id"] in local_ids]
    for key in ("trays", "node_records", "edge_records", "node_contracts", "edge_contracts",
                "transfers", "known_faults", "route_requests", "recovery_requests", "version"):
        assert compact[key] == full[key]
    assert [m for m in compact["delivered_messages"] if m["kind"] == "service_forecast"] == [
        m for m in full["delivered_messages"] if m["kind"] == "service_forecast"]
    assert session.demand_signature(owner) == expected_signature(full)
    assert session.offline_state_sha256() == before
    assert session.observe(owner) == full
    return compact


@pytest.mark.parametrize("trays", [1, 3, 11])
def test_native_fifo_counts_and_representatives_scale_with_real_trays(native, trays):
    session = native.NativeSession(queue_fixture(trays=trays))
    session.advance_to(.1)
    compact = assert_public_projection(session, "A")
    projection = compact["control_projection"]
    assert projection["candidate_limit"] == trays
    group, = projection["waiting_groups"]
    assert group["count"] == 200 - trays
    assert len(group["jobs"]) == 2 * trays  # actual finite-inventory bound, never a fixed K
    assert len(compact["jobs"]) == trays
    assert session.result_at(.1)["population"]["offered_by_horizon"] == 200


def test_zero_supply_keeps_exact_remote_demand_without_expanding_identities(native):
    session = native.NativeSession(queue_fixture(count=500))
    session.advance_to(.1)
    session.publish_demand("A", "B", .2)
    assert session.observe_control("B")["control_projection"]["exact_waiting_count"] == 0
    session.advance_to(.31)
    compact = assert_public_projection(session, "B")
    projection = compact["control_projection"]
    assert projection["candidate_limit"] == 0
    assert projection["exact_waiting_count"] == 499
    assert projection["waiting_groups"][0]["jobs"] == []
    assert compact["delivered_messages"][0]["jobs"] == []
    assert compact["delivered_messages"][0]["snapshot_waiting_count"] == 499
    assert session.result_at(.31)["population"]["offered_by_horizon"] == 500


def test_latest_same_time_publication_wins_even_when_old_empty_snapshot_arrives_late(native):
    data = queue_fixture(count=10, trays=0)
    data["trays"] = [dict(tray_id="remote-tray", node=4)]
    data["jobs"] = [dict(j, arrival=0) for j in data["jobs"]]
    session = native.NativeSession(data)
    session.publish_demand("A", "B", 1)  # no arrival event processed yet
    session.advance_to(0)
    session.publish_demand("A", "B", 0)
    session.advance_to(0)
    first = assert_public_projection(session, "B")
    assert first["control_projection"]["exact_waiting_count"] == 10
    session.advance_to(1)
    second = assert_public_projection(session, "B")
    assert second["control_projection"]["exact_waiting_count"] == 10
    assert second["delivered_messages"][0]["publication_sequence"] == 2


def test_local_loaded_contract_shadows_remote_stale_waiting_snapshot(native):
    data = tiny_cycle()
    data["jobs"] = [dict(data["jobs"][0], storage_release_at=0, storage_min_dwell=0)]
    data["trays"] = [dict(tray_id="T0", node=4)]
    data["transfers"] = []
    session = native.NativeSession(data)
    session.advance_to(0)
    session.publish_demand("A", "B", 0)
    session.advance_to(0)
    assert session.observe_control("B")["control_projection"]["exact_waiting_count"] == 1
    assert session.submit_transfer_intent(dict(request_id="live:bring-to-loader", owner_id="B", tray_id="T0",
        source=4, destination=0, message_delay=0, earliest_departure=0, expiry=60))["status"] == "pending"
    # Actual EDGE_EXIT into B occurs at 5.45 (node 3), then 6.50 (node 4).
    # By t=10 hold has finished and the tray no longer carries this remote
    # contract, so that later observation cannot exercise the shadow case.
    session.advance_to(6.5)
    full = session.observe("B")
    assert any(j["business_bag_id"] == "B1" and j["status"] != "waiting_for_tray" for j in full["jobs"])
    compact = assert_public_projection(session, "B")
    assert compact["control_projection"]["exact_waiting_count"] == 0
    assert compact["control_projection"]["known_origin_nodes"] == [0]


def test_future_tape_and_unrelated_owner_do_not_change_compact_projection_or_signature(native):
    first = queue_fixture(count=20)
    second = deepcopy(first)
    second["jobs"].append(dict(second["jobs"][0], business_bag_id="unseen-future", origin=4, destination=0, arrival=50))
    a, b = native.NativeSession(first), native.NativeSession(second)
    for session in (a, b):
        session.advance_to(.1)
        session.publish_demand("A", "B", 0)
        session.advance_to(.1)
    assert a.offline_state_sha256() != b.offline_state_sha256()
    for owner in ("A", "B"):
        assert a.observe_control(owner) == b.observe_control(owner)
        assert a.demand_signature(owner) == b.demand_signature(owner)
    with pytest.raises(ValueError, match="unknown_observation_owner"):
        a.observe_control("unknown")
    with pytest.raises(ValueError, match="unknown_observation_owner"):
        a.demand_signature("unknown")


def test_compact_projection_preserves_delayed_forecast_withdrawals_and_checkpoint(native):
    data = tiny_cycle()
    data["transfers"] = []
    data["node_contracts"][1]["resource_owner"] = "B"
    session = native.NativeSession(data)
    session.advance_to(.05)
    original = session.publish_service_forecast("A", "B", "T0", 1, .4)
    session.withdraw_service_forecast("A", original["message_id"], .1)
    session.advance_to(.15)
    assert_public_projection(session, "B")
    fork = session.fork()
    for target in (session, fork):
        target.advance_to(.45)
        compact = assert_public_projection(target, "B")
        assert len([m for m in compact["delivered_messages"] if m["kind"] == "service_forecast"]) == 2
    assert session.observe_control("B") == fork.observe_control("B")
    assert session.offline_state_sha256() == fork.offline_state_sha256()
