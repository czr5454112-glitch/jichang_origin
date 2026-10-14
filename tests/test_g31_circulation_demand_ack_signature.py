"""Demand ACK content identifies the immutable execution-time snapshot."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import struct

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session_011/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def scene(**config):
    value = tiny_cycle(); value["transfers"] = []
    value["owner_protocol"] = dict(enabled=True, timeout=.1, ack_delay=.05, **config)
    return value


def demand(suffix="one", **extra):
    result = dict(request_id=f"live:1:A:demand:{suffix}", owner_id="A", kind="demand", target_owner="B",
                  message_delay=0., publication_delay=0.)
    result.update(extra); return result


def known(session, request):
    return session.protocol_command("A", request["request_id"]).get("last_delivered_ack")


def canonical(jobs):
    rows = sorted((j["business_bag_id"], j["origin"], j["arrival"], j["deadline"]) for j in jobs)
    data = bytearray(b"g31.demand_signature.v1\n") + struct.pack(">Q", len(rows))
    for name, origin, arrival, deadline in rows:
        identity = name.encode("utf-8")
        data += struct.pack(">Q", len(identity)) + identity
        data += struct.pack(">qdd", origin, arrival if arrival else 0., deadline if deadline else 0.)
    return dict(schema="g31.demand_signature.v1", sha256=hashlib.sha256(data).hexdigest(), waiting_count=len(rows))


def test_actual_capture_signature_differs_from_submission_and_later_aba_queue(native):
    value = scene()
    value["trays"] = [dict(tray_id="T0", node=5)]
    # A real cross-owner return: same-zone redistribution is intentionally
    # outside this controller's authority and must remain rejected.
    next(n for n in value["node_contracts"] if n["node"] == 5)["zone"] = "B"
    value["jobs"] = [dict(value["jobs"][0], business_bag_id="Y", arrival=.1)]
    value["edge_records"] = [(u, v, .25 if (u, v) == (5, 0) else length, speed)
                             for u, v, length, speed in value["edge_records"]]
    value = prepare_input(value)
    s = native.NativeSession(value); s.advance_to(0.)
    submitted_signature = s.protocol_demand_signature("A")
    request = demand(message_delay=.2)
    s.submit_protocol_command(request)
    s.submit_protocol_transfer(dict(request_id="live:1:B:real-tray-return", owner_id="B", tray_id="T0",
        source=5, destination=0, earliest_departure=0., expiry=10., message_delay=0.))
    s.advance_to(.35)
    assert submitted_signature == s.protocol_demand_signature("A") == canonical([])
    ack = known(s, request)
    message, = s.observe_protocol("B")["delivered_messages"]
    assert [j["business_bag_id"] for j in message["jobs"]] == ["Y"]
    assert ack["captured_demand_signature"] == canonical(message["jobs"]) != submitted_signature
    assert ack["captured_demand_observed_at"] == .2
    assert ack["captured_demand_publication_sequence"] == message["publication_sequence"]
    prefix = s.result_at(.35)
    assert prefix["jobs"][0]["status"] == "loading"
    assert prefix["transfers"][0]["received_at"] == pytest.approx(.35)
    assert [r["time"] for r in prefix["receipts"] if r["event"] == "LOAD_START" and
            r["business_bag_id"] == "Y"] == pytest.approx([.35])
    assert s.result_at(.45)["jobs"][0]["loaded_at"] == pytest.approx(.45)


def test_old_pending_ack_never_gains_the_later_final_capture_fields(native):
    s = native.NativeSession(scene()); s.advance_to(.3)
    request = demand(publication_delay=2.)
    s.submit_protocol_command(request); s.advance_to(.31)
    s.submit_protocol_command(request); s.advance_to(.4)
    pending = deepcopy(known(s, request))
    assert pending["status"] == "pending_delivery"
    assert "captured_demand_signature" not in pending
    s.advance_to(2.4)
    final = known(s, request)
    assert final["status"] == "delivered" and final["captured_demand_signature"]["waiting_count"] == 1
    history = s.observe_protocol("A")["delivered_command_acks"]
    old = next(a for a in history if a["sequence"] == pending["sequence"])
    assert "captured_demand_signature" not in old
    assert all(old[k] == v for k, v in pending.items())


def test_lost_final_ack_hides_capture_until_actual_retry_ack_arrives(native):
    s = native.NativeSession(scene(drop_ack_packets=1)); s.advance_to(.3)
    request = demand(); s.submit_protocol_command(request); s.advance_to(.5)
    assert known(s, request) is None
    assert s.observe_protocol("A")["delivered_command_acks"] == []
    s.submit_protocol_command(request)
    assert known(s, request) is None
    s.advance_to(.56)
    message, = s.observe_protocol("B")["delivered_messages"]
    assert known(s, request)["captured_demand_signature"] == canonical(message["jobs"])
    assert s.protocol_command("B", request["request_id"])["status"] == "unknown_request"


def test_recipient_outage_preserves_actual_source_capture_identity(native):
    s = native.NativeSession(scene(owner_outages=[dict(owner="B", start=0., end=1.)]))
    s.advance_to(.3); request = demand(); s.submit_protocol_command(request); s.advance_to(.9)
    assert known(s, request) is None
    s.advance_to(1.1)
    ack = known(s, request); message, = s.observe_protocol("B")["delivered_messages"]
    assert ack["captured_demand_observed_at"] == .3
    assert ack["completed_at"] == message["delivered_at"] == 1.
    assert ack["captured_demand_signature"] == canonical(message["jobs"])


def test_canonical_unicode_order_and_signed_zero_match_local_signature(native):
    value = scene(); value["trays"] = [dict(tray_id="T0", node=4)]
    template = value["jobs"][0]
    value["jobs"] = [dict(template, business_bag_id=name, arrival=-0. if i % 2 else 0., deadline=40.)
                     for i, name in enumerate(["z", "托盘", "a", "é", "😀"])]
    s = native.NativeSession(value); s.advance_to(.01)
    request = demand(); s.submit_protocol_command(request); s.advance_to(.1)
    expected = canonical(value["jobs"])
    assert s.protocol_demand_signature("A") == known(s, request)["captured_demand_signature"] == expected


def test_snapshot_digest_cache_is_readonly_and_rebuilt_after_restore(native):
    first, second = scene(), scene()
    first["jobs"][1]["business_bag_id"] = "first"
    second["jobs"][1]["business_bag_id"] = "second"
    a, b = native.NativeSession(first), native.NativeSession(second)
    request = demand()
    for s in (a, b):
        s.advance_to(.3); s.submit_protocol_command(request); s.advance_to(.4)
    before = a.offline_state_sha256()
    original = known(a, request); other = known(b, request)
    assert original["captured_demand_signature"] != other["captured_demand_signature"]
    corrupt_return = known(a, request); corrupt_return["captured_demand_signature"]["sha256"] = "corrupted"
    assert known(a, request) == original
    assert a.offline_state_sha256() == before
    b.restore(a.checkpoint())
    assert known(b, request) == original
    fork = a.fork()
    assert known(fork, request) == original
    assert fork.offline_state_sha256() == before


def test_historical_ack_matches_its_message_after_a_newer_snapshot(native):
    s = native.NativeSession(scene()); s.advance_to(.05)
    first = demand("first"); s.submit_protocol_command(first); s.advance_to(.15)
    old = deepcopy(known(s, first)); assert old["captured_demand_signature"]["waiting_count"] == 0
    s.advance_to(.3); second = demand("second"); s.submit_protocol_command(second); s.advance_to(.4)
    assert known(s, second)["captured_demand_signature"]["waiting_count"] == 1
    assert known(s, first) == old
    assert known(s, second)["captured_demand_publication_sequence"] > old["captured_demand_publication_sequence"]
