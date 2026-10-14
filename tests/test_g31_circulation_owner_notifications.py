"""Actual owner-local event wakes; no native heap/remote future oracle."""
from copy import deepcopy
import os
import math
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session_015/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def scene(quiet=False, **protocol):
    value = tiny_cycle(); value["transfers"] = []
    value["owner_protocol"] = dict(enabled=True, timeout=1., ack_delay=0., **protocol)
    value["owner_notifications"] = dict(enabled=True)
    if quiet:
        value["jobs"] = []
    return value


def advance(session, owners=("A", "B"), after=None, horizon=40., budget=1000000):
    return session.advance_until_owner_notification(list(owners), after or {o: 0 for o in owners}, horizon, budget)


def drain(session, horizon=40., owners=("A", "B"), after=None):
    cursor = after or {o: 0 for o in owners}; rows = []
    for _ in range(10000):
        row = advance(session, owners, cursor, horizon)
        assert row["timestamp_complete"] and row["status"] != "budget_exhausted"
        assert all(n["observed_at"] <= row["physical_time"] for n in row["notifications"].values())
        rows.append(row)
        cursor.update({o: n["sequence"] for o, n in row["notifications"].items()})
        if row["horizon_complete"]:
            return rows, cursor
    raise AssertionError("unbounded notification drain")


def demand(owner="A", target="B", suffix="1", **extra):
    request = dict(request_id=f"live:1:{owner}:demand:{suffix}", owner_id=owner, kind="demand",
                   target_owner=target, message_delay=0., publication_delay=0.)
    request.update(extra); return request


def test_disabled_explicit_false_preserves_seal_and_physics(native):
    first = scene(); first.pop("owner_notifications")
    second = deepcopy(first); second["owner_notifications"] = dict(enabled=False)
    a, b = native.NativeSession(first), native.NativeSession(second)
    for time in (0., .1, 2., 10., 40.):
        a.advance_to(time); b.advance_to(time)
        assert a.offline_state_sha256() == b.offline_state_sha256()
        assert a.observe_protocol("A") == b.observe_protocol("A")
    assert a.result_at(40.)["receipts"] == b.result_at(40.)["receipts"]
    with pytest.raises(ValueError, match="owner_notifications_not_enabled"):
        advance(a)


def test_enabled_wakes_do_not_change_native_physical_execution(native):
    value = scene(); plain = deepcopy(value); plain.pop("owner_notifications")
    a, b = native.NativeSession(value), native.NativeSession(plain)
    rows, _ = drain(a); b.advance_to(40.)
    assert any(r["status"] == "notified" for r in rows)
    left, right = a.result_at(40.), b.result_at(40.)
    for key in ("jobs", "trays", "transfers", "receipts", "decisions", "population"):
        assert left[key] == right[key]


def test_zero_duration_load_drains_all_same_time_phases(native):
    value = scene(); value["jobs"][0]["load_seconds"] = 0.
    s = native.NativeSession(value)
    row = advance(s)
    assert row["physical_time"] == 0. and row["timestamp_complete"]
    assert row["notifications"]["A"]["change_mask"] & 3 == 3
    local = s.observe_protocol("A")
    assert local["trays"][0]["mode"] != "loading"
    result = s.result_at(0.)
    events = {r["event"] for r in result["receipts"] if r["time"] == 0.}
    assert {"LOAD_START", "LOAD_COMPLETE"} <= events


def test_partial_timestamp_budget_withholds_notifications_then_restores(native):
    value = scene(); value["jobs"][0]["load_seconds"] = 0.
    s = native.NativeSession(value)
    row = advance(s, budget=1)
    assert row["status"] == "budget_exhausted" and not row["timestamp_complete"]
    assert not row["horizon_complete"] and row["notifications"] == {}
    with pytest.raises(ValueError, match="notification_timestamp_incomplete"):
        s.owner_notifications(["A"])
    branch = s.fork(); checkpoint = s.checkpoint()
    recovered = advance(s)
    assert recovered == advance(branch)
    assert recovered["status"] == "notified" and recovered["physical_time"] == 0.
    s.restore(checkpoint)
    assert advance(s) == recovered
    assert s.offline_state_sha256() == branch.offline_state_sha256()


def test_checkpoint_fork_preserves_all_notification_continuations(native):
    s = native.NativeSession(scene()); row = advance(s)
    cursor = {o: row["notifications"].get(o, {}).get("sequence", 0) for o in ("A", "B")}
    checkpoint = s.checkpoint(); branch = s.fork()
    expected = drain(s, after=cursor.copy())
    assert drain(branch, after=cursor.copy()) == expected
    assert s.offline_state_sha256() == branch.offline_state_sha256()
    s.restore(checkpoint)
    assert drain(s, after=cursor.copy()) == expected


@pytest.mark.parametrize("private_kind", ["future_job", "remote_job", "remote_physics", "remote_fault", "hidden_outage"])
def test_private_events_do_not_change_other_owner_revision_or_wake(native, private_kind):
    base = scene(quiet=True); changed = deepcopy(base)
    if private_kind in ("future_job", "remote_job", "remote_physics"):
        changed["jobs"] = [dict(tiny_cycle()["jobs"][0], business_bag_id="private",
                                origin=3, destination=4, storage_node=-1,
                                arrival=50. if private_kind == "future_job" else .25)]
        if private_kind == "remote_physics":
            changed["trays"].append(dict(tray_id="private-B-tray", node=3))
    elif private_kind == "remote_fault":
        changed["faults"] = [dict(**{"from": 3, "to": 4}, start=.25, end=1.25, message_delay=.1)]
    else:
        changed["owner_protocol"]["owner_outages"] = [dict(owner="B", start=.25, end=1.25)]
    a, b = native.NativeSession(base), native.NativeSession(changed)
    assert advance(a, ("A",), horizon=2.) == advance(b, ("A",), horizon=2.)
    assert a.owner_notifications(["A"]) == b.owner_notifications(["A"])
    assert a.observe_protocol("A") == b.observe_protocol("A")
    if private_kind == "remote_physics":
        result = b.result_at(2.)
        assert result["jobs"][0]["status"] == "completed"
        assert any(r["event"] == "EDGE_EXIT" and r["tray_id"] == "private-B-tray" for r in result["receipts"])


def test_ack_drop_hidden_but_actual_timeout_and_retry_ack_wake(native):
    value = scene(quiet=True, drop_ack_packets=1)
    s = native.NativeSession(value); request = demand()
    s.submit_protocol_command(request)
    # Peer actually receives the demand at zero; A sees neither processing nor drop.
    row = advance(s, ("A",), horizon=.5)
    assert row["status"] == "horizon_reached" and row["notifications"] == {}
    row = advance(s, ("A",), horizon=1.)
    assert row["notifications"]["A"]["change_mask"] == 32
    cursor = {"A": row["notifications"]["A"]["sequence"]}
    s.submit_protocol_command(request)
    row = advance(s, ("A",), cursor, horizon=1.)
    assert row["status"] == "notified" and row["physical_time"] == 1.
    assert row["notifications"]["A"]["change_mask"] & 16
    assert s.protocol_command("A", request["request_id"])["last_delivered_ack"]["status"] == "delivered"


def test_real_peer_delivery_and_same_time_ack_trigger_individual_owners(native):
    s = native.NativeSession(scene(quiet=True)); s.advance_to(0.)
    request = demand(publication_delay=.2)
    s.submit_protocol_command(request)
    row = advance(s, horizon=1.)
    assert row["physical_time"] == .2
    assert row["notifications"]["A"]["change_mask"] == 16
    assert row["notifications"]["B"]["change_mask"] == 4
    cursor = {o: n["sequence"] for o, n in row["notifications"].items()}
    request = demand(suffix="2")
    s.submit_protocol_command(request)
    again = advance(s, after=cursor, horizon=.2)
    assert again["physical_time"] == .2 and again["horizon_complete"]
    assert all(again["notifications"][o]["sequence"] > cursor[o] for o in cursor)


def test_duplicate_ack_notifies_only_when_delivered(native):
    s = native.NativeSession(scene(quiet=True, duplicate_acks=True, duplicate_ack_delay=.3))
    s.submit_protocol_command(demand())
    first = advance(s, ("A",), horizon=1.)
    second = advance(s, ("A",), {"A": first["notifications"]["A"]["sequence"]}, 1.)
    assert first["physical_time"] == 0. and second["physical_time"] == .3
    assert second["notifications"]["A"]["change_mask"] == 16


def test_local_fault_wakes_only_after_actual_notification(native):
    value = scene(quiet=True)
    value["faults"] = [dict(**{"from": 0, "to": 1}, start=.25, end=2., message_delay=.5)]
    s = native.NativeSession(value)
    row = advance(s, ("A",), horizon=.5)
    assert row["status"] == "horizon_reached" and row["notifications"] == {}
    row = advance(s, ("A",), horizon=1.)
    assert row["physical_time"] == .75 and row["notifications"]["A"]["change_mask"] == 64


def test_preinitialized_fault_heap_is_rebuilt_for_strict_circulation_time(native):
    value = scene(quiet=True)
    later = math.nextafter(1., math.inf)
    # initialize() enqueues the fault tape before circulation is configured.
    # Input sequence deliberately opposes exact numeric time by one ULP.
    value["faults"] = [dict(**{"from": 0, "to": 1}, start=later, end=3., message_delay=0.),
                       dict(**{"from": 0, "to": 6}, start=1., end=2., message_delay=0.)]
    s = native.NativeSession(value)
    first = advance(s, ("A",), horizon=later)
    assert first["physical_time"] == 1. and not first["horizon_complete"]
    cursor = {"A": first["notifications"]["A"]["sequence"]}
    second = advance(s, ("A",), cursor, horizon=later)
    assert second["physical_time"] == later and second["horizon_complete"]
    assert second["notifications"]["A"]["sequence"] > cursor["A"]


def test_positive_sub_epsilon_fault_delay_is_not_delivered_early(native):
    value = scene(quiet=True); delivered = 1.+1.e-10
    value["faults"] = [dict(**{"from": 0, "to": 1}, start=1., end=3., message_delay=1.e-10)]
    s = native.NativeSession(value)
    before = advance(s, ("A",), horizon=math.nextafter(delivered, -math.inf))
    assert before["notifications"] == {} and before["horizon_complete"]
    after = advance(s, ("A",), horizon=delivered)
    assert after["physical_time"] == delivered and after["notifications"]["A"]["change_mask"] == 64


def test_zero_delay_dropped_fault_does_not_notify(native):
    value = scene(quiet=True)
    value["faults"] = [dict(**{"from": 0, "to": 1}, start=1., end=3., message_delay=0., drop_notification=True)]
    s = native.NativeSession(value)
    assert advance(s, ("A",), horizon=2.)["notifications"] == {}


@pytest.mark.parametrize("owners,cursor,match", [(["A"], {"B": 0}, "cursor_keys"),
    (["A", "A"], {"A": 0}, "duplicate_notification_owner"), (["A"], {"A": 1}, "future_owner"),
    (["missing"], {"missing": 0}, "unknown"), ([], {}, "invalid_notification")])
def test_invalid_cursor_does_not_mutate_state(native, owners, cursor, match):
    s = native.NativeSession(scene(quiet=True)); before = s.offline_state_sha256()
    with pytest.raises((ValueError, RuntimeError), match=match):
        s.advance_until_owner_notification(owners, cursor, 1.)
    assert s.offline_state_sha256() == before


def test_notifications_require_real_owner_protocol(native):
    value = scene(); value.pop("owner_protocol")
    with pytest.raises(ValueError, match="notifications_require_owner_protocol"):
        native.NativeSession(value)


@pytest.mark.parametrize("notifications", [True, False])
def test_adjacent_float_ack_is_delivered_before_later_physical_service(native, notifications):
    value = scene(); value["owner_notifications"]["enabled"] = notifications
    value["jobs"] = [dict(value["jobs"][0], load_seconds=0.)]
    value["node_records"] = [(n, kind, 6.05 if n == 0 else duration, x, y, edges)
                             for n, kind, duration, x, y, edges in value["node_records"]]
    s = native.NativeSession(prepare_input(value)); s.advance_to(0.)
    before_service = math.nextafter(6.05, -math.inf)
    request = demand(publication_delay=before_service)
    s.submit_protocol_command(request)
    if notifications:
        rows, cursor = drain(s, horizon=before_service)
        assert all(r["physical_time"] <= before_service for r in rows)
    else:
        assert s.advance_to(before_service)["horizon_complete"]
    assert s.physical_time == before_service
    message, = s.observe_protocol("B")["delivered_messages"]
    assert message["delivered_at"] == before_service
    assert s.protocol_command("A", request["request_id"])["last_delivered_ack"]["delivered_at"] == before_service
    assert not any(r["event"] == "EDGE_ENTER" for r in s.result_at(before_service)["receipts"])
    s.advance_to(6.05)
    assert s.physical_time == 6.05


@pytest.mark.parametrize("service,load,expected", [(2., 0., 2.), (3., 0., 3.), (.001, 3., 3.001)])
def test_forecast_uses_committed_remaining_service_and_exact_tie(native, service, load, expected):
    value = scene(); value["jobs"] = [dict(value["jobs"][0], load_seconds=load)]
    value["node_records"] = [tuple([n, kind, service if n == 0 else duration, x, y, edges])
                             for n, kind, duration, x, y, edges in value["node_records"]]
    next(n for n in value["node_contracts"] if n["node"] == 1)["resource_owner"] = "B"
    value = prepare_input(value)
    s = native.NativeSession(value); advance(s, horizon=0.)
    request = dict(request_id="live:1:A:forecast", owner_id="A", kind="service_forecast",
                   target_owner="B", tray_id="T0", next=1, message_delay=2., publication_delay=.5)
    s.submit_protocol_command(request); drain(s, horizon=4.)
    ack = s.protocol_command("A", request["request_id"])["last_delivered_ack"]
    assert ack["status"] == "delivered"
    forecasts = s.observe_protocol("B")["delivered_messages"]
    forecast = next(f for f in forecasts if f["message_id"] == ack["result_id"])
    actual = [r["time"] for r in s.result_at(4.)["receipts"]
              if r["event"] == "EDGE_ENTER" and r["from"] == 0 and r["to"] == 1]
    assert actual == pytest.approx([expected])
    assert forecast["entry_estimate"] == pytest.approx(expected)
    # Delivery may occur after the predicted entry; this is no release guarantee.
    assert forecast["observed_at"] == 2.
