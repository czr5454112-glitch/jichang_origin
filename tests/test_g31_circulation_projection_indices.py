"""Native024 static FIFO indexing must preserve the complete lawful projection."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.validate_protocol_control import scenarios


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def ordered(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def views(session, protocol=True):
    if not protocol:
        return [{"full": session.observe(o), "compact": session.observe_control(o)} for o in ("A", "B")]
    return [{"full": session.observe_protocol(o), "compact": session.observe_protocol_control(o),
             "policy": session.observe_protocol_control_policy(o),
             "recent": session.observe_protocol_control_policy_recent(o, 1.),
             "demand": session.protocol_demand_signature(o),
             "planning": session.protocol_planning_snapshots(o)} for o in ("A", "B")]


def equivalent(session, protocol=True):
    seal = session.offline_state_sha256()
    session._set_indexed_control_projection(False)
    old = views(session, protocol)
    session._set_indexed_control_projection(True)
    indexed = views(session, protocol)
    assert ordered(old) == ordered(indexed)
    assert session.offline_state_sha256() == seal
    # A caller changing returned nested containers must not affect either arm.
    indexed[0]["compact"]["control_projection"]["waiting_groups"].clear()
    assert ordered(views(session, protocol)) == ordered(old)
    return old


@pytest.mark.parametrize("protocol", [False, True])
@pytest.mark.parametrize("size", [7, 4000])
def test_input_order_equal_arrivals_unicode_signed_zero_and_future_filter(native, protocol, size):
    data = tiny_cycle(); data["transfers"] = []
    data["trays"] = [{"tray_id": "TA", "node": 5}, {"tray_id": "TB", "node": 3}]
    if protocol:
        data["owner_protocol"] = {"enabled": True, "timeout": .1, "ack_delay": .01}
    template = data["jobs"][0]
    names = ["z", "托盘", "a", "é", "😀", "a:" + "x"*500, "future"]
    data["jobs"] = [dict(template, business_bag_id=f"{names[i%7]}:{i:04d}",
                         arrival=50. if i%7 == 6 else (0. if i%2 else -0.),
                         origin=4 if i%3 == 0 else 0,
                         destination=0 if i%3 == 0 else 4) for i in reversed(range(size))]
    session = native.NativeSession(data); session.advance_to(.01)
    before = equivalent(session, protocol)
    for source, target in (("A", "B"), ("B", "A")):
        if protocol:
            session.submit_protocol_command(dict(request_id=f"live:1:{source}:queue", owner_id=source,
                kind="demand", target_owner=target, message_delay=0., publication_delay=0.))
        else:
            session.publish_demand(source, target, 0.)
    session.advance_to(.01)
    full = equivalent(session, protocol)
    for rows in full:
        projection = rows["compact"]["control_projection"]
        assert projection["exact_waiting_count"] == sum(i%7 != 6 for i in range(size))
        assert all(not j["business_bag_id"].startswith("future:") for group in projection["waiting_groups"] for j in group["jobs"])
    checkpoint = session.checkpoint(); expected = ordered(full)
    other = deepcopy(data); other["jobs"].reverse()
    restored = native.NativeSession(other); restored._set_indexed_control_projection(False)
    restored.restore(checkpoint)
    assert ordered(equivalent(restored, protocol)) == expected
    session._set_indexed_control_projection(False)
    branch = session.fork()
    assert ordered(equivalent(branch, protocol)) == expected
    # Newly released future contracts are filtered at each call, never cached.
    session.advance_to(50.)
    assert ordered(equivalent(session, protocol)) != ordered(before)


@pytest.mark.parametrize("protocol", [False, True])
def test_newer_same_time_capture_and_local_loaded_shadow_after_owner_crossing(native, protocol):
    data = tiny_cycle(); data["transfers"] = []
    data["jobs"] = [dict(data["jobs"][0], storage_release_at=0., storage_min_dwell=0.)]
    data["trays"] = [{"tray_id": "T0", "node": 4}]
    if protocol:
        data["owner_protocol"] = {"enabled": True, "timeout": .1, "ack_delay": .01}
    session = native.NativeSession(data)
    if not protocol:
        session.publish_demand("A", "B", 1.)  # old empty capture at the same clock
    session.advance_to(0.)
    if protocol:
        for suffix, delay in (("late", 1.), ("new", 0.)):
            session.submit_protocol_command(dict(request_id="live:1:A:"+suffix, owner_id="A", kind="demand",
                target_owner="B", message_delay=0., publication_delay=delay))
    else:
        session.publish_demand("A", "B", 0.)
    session.advance_to(0.)
    assert equivalent(session, protocol)[1]["compact"]["control_projection"]["exact_waiting_count"] == 1
    session.advance_to(1.)
    equivalent(session, protocol)
    payload = dict(request_id="live:1:B:return", owner_id="B", tray_id="T0", source=4, destination=0,
                   message_delay=0., earliest_departure=session.physical_time, expiry=60.)
    submit = session.submit_protocol_transfer if protocol else session.submit_transfer_intent
    assert submit(payload)["status"] == "pending"
    session.advance_to(7.5)
    projection = equivalent(session, protocol)[1]["compact"]["control_projection"]
    assert projection["exact_waiting_count"] == 0
    assert projection["known_origin_nodes"] == [0]
    assert any(j["status"] != "waiting_for_tray" for j in views(session, protocol)[1]["full"]["jobs"])
    equivalent(session.fork(), protocol)


@pytest.mark.parametrize("bad", ["duplicate", "nan", "infinite"])
def test_dense_identity_and_total_order_preconditions_are_native_validated(native, bad):
    data = tiny_cycle()
    if bad == "duplicate": data["jobs"][1]["business_bag_id"] = data["jobs"][0]["business_bag_id"]
    else: data["jobs"][0]["arrival"] = float("nan" if bad == "nan" else "inf")
    with pytest.raises((ValueError, RuntimeError), match="invalid_job"):
        native.NativeSession(data)


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in {
            "wall_seconds", "compute_wall_ms", "compute_cpu_ms", "submit_compute_ms", "wall_ms", "cpu_ms"}}
    if isinstance(value, list): return [semantic(v) for v in value]
    return value


@pytest.mark.parametrize("name,data,owners", scenarios())
def test_toggle_preserves_complete_fault_policy_request_state_and_native_tape(native, name, data, owners):
    records = []
    for indexed in (False, True):
        value = deepcopy(data); value["owner_notifications"] = {"enabled": True}
        session = native.NativeSession(value); session._set_indexed_control_projection(indexed)
        state = None; parts = []
        for _ in range(1000):
            part = run_event_protocol_control(session, owners, horizon=20., event_budget=100000,
                max_activations=25, state=state, control_period=.5, command_delay=.01,
                publication_delay=.02, retry_period=.5, lease_seconds=120.)
            state = part["controller_state"]; parts.append(part)
            if part["status"] != "control_budget_exhausted": break
        assert part["status"] == "reached"
        records.append((ordered(semantic(parts)), session.offline_state_sha256()))
    assert records[0] == records[1], name
