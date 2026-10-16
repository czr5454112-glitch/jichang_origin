"""Derived observation indexes must not survive a different restored history."""
from copy import deepcopy
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def scene():
    data = tiny_cycle()
    data["transfers"] = []
    data["owner_protocol"] = {"enabled": True, "timeout": .3, "ack_delay": .01}
    return data


def observe_all(session):
    return {(o, compact): session.observe_protocol_control(o) if compact else session.observe_protocol(o)
            for o in ("A", "B") for compact in (False, True)}


def test_warm_indexes_do_not_change_physics_or_escape_returned_dicts(native):
    session = native.NativeSession(scene())
    session.advance_to(3.)
    before = session.offline_state_sha256()
    expected = observe_all(session)
    for _ in range(3):
        observed = observe_all(session)
        assert observed == expected
        observed[("A", False)]["trays"].clear()
        observed[("A", True)]["node_contracts"][0]["capacity"] = 999
    assert session.offline_state_sha256() == before
    assert observe_all(session) == expected


def test_restore_discards_larger_request_history_and_reused_identity(native):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    checkpoint = session.checkpoint()
    request = {"request_id": "live:1:A:reused", "owner_id": "A", "kind": "demand",
               "target_owner": "B", "message_delay": .01, "publication_delay": .01}
    assert session.submit_protocol_command(request)["status"] == "pending"
    session.advance_to(.1)
    assert session.protocol_command("A", request["request_id"])["last_delivered_ack"]["status"] == "delivered"
    observe_all(session)
    session.restore(checkpoint)
    assert session.protocol_command("A", request["request_id"])["status"] == "unknown_request"
    changed = {**request, "publication_delay": .2}
    session.submit_protocol_command(changed)
    session.advance_to(.1)
    assert "last_delivered_ack" not in session.protocol_command("A", request["request_id"])
    assert not session.observe_protocol("B")["delivered_messages"]
    session.advance_to(.3)
    ack = session.protocol_command("A", request["request_id"])["last_delivered_ack"]
    assert ack["status"] == "delivered" and ack["completed_at"] == .01 + .2


@pytest.mark.parametrize("time", [.05, .12, 1.2, 3., 8.2, 12.])
def test_restore_and_fork_have_exact_views_after_receipt_index_warming(native, time):
    session = native.NativeSession(scene())
    session.advance_to(time)
    checkpoint = session.checkpoint()
    expected = observe_all(session)
    branch = session.fork()
    assert observe_all(branch) == expected
    session.advance_to(30.)
    observe_all(session)
    session.restore(checkpoint)
    assert observe_all(session) == expected
    assert session.offline_state_sha256() == branch.offline_state_sha256()


def test_future_origin_contracts_do_not_change_current_projection(native):
    a = scene()
    b = deepcopy(a)
    for i in range(50):
        b["jobs"].append({**b["jobs"][0], "business_bag_id": f"future{i}", "arrival": 1000. + i})
    x, y = native.NativeSession(a), native.NativeSession(b)
    x.advance_to(.1)
    y.advance_to(.1)
    assert observe_all(x) == observe_all(y)
