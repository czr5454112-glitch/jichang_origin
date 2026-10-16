"""Native026 derived indexes: full public/API/order/state parity with optout."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control
from scripts.experiments.g31_ics_circulation.validate_protocol_control import scenarios


@pytest.fixture(scope="module")
def native():
    module = load_native(os.environ["G31_CIRCULATION_BINARY"])
    assert hasattr(module.NativeSession, "_set_indexed_message_selection")
    return module


def ordered(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def scene(**protocol):
    data = tiny_cycle(); data["transfers"] = []
    data["jobs"] = [dict(data["jobs"][0], load_seconds=30., allow_suffix_reroute=True)]
    next(n for n in data["node_contracts"] if n["node"] == 1)["resource_owner"] = "B"
    data["owner_protocol"] = dict(enabled=True, timeout=.4, ack_delay=.02, **protocol)
    data["owner_notifications"] = {"enabled": True}
    return data


def views(session, requests=(), validity=1.):
    result = []
    for owner in ("A", "B"):
        result.append(dict(full=session.observe_protocol(owner),
            compact=session.observe_protocol_control(owner),
            policy=session.observe_protocol_control_policy(owner),
            recent=session.observe_protocol_control_policy_recent(owner, validity),
            demand=session.protocol_demand_signature(owner),
            commands=[session.protocol_command(owner, request) for request in requests if f":{owner}:" in request]))
    return result


def equivalent(session, requests=(), validity=1.):
    seal = session.offline_state_sha256()
    session._set_indexed_message_selection(False)
    old = views(session, requests, validity)
    session._set_indexed_message_selection(True)
    new = views(session, requests, validity)
    assert ordered(old) == ordered(new)
    assert session.offline_state_sha256() == seal
    new[0]["full"]["delivered_messages"].clear()
    new[1]["compact"]["control_projection"]["waiting_groups"].clear()
    assert ordered(views(session, requests, validity)) == ordered(old)
    return old


@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 1},
    {"duplicate_acks": True, "duplicate_ack_delay": .001},
    {"owner_outages": [{"owner": "B", "start": .05, "end": .8}]}])
def test_native_delayed_old_duplicate_retry_ack_expiry_restore_and_toggle(native, protocol):
    session = native.NativeSession(scene(**protocol)); session.advance_to(0.)
    payloads = []
    def submit(name, kind, **extra):
        payload = dict(request_id="live:1:A:"+name, owner_id="A", kind=kind,
            message_delay=0., publication_delay=0., **extra)
        payloads.append(payload); session.submit_protocol_command(payload)
    submit("old", "service_forecast", target_owner="B", tray_id="T0", next=1)
    session.advance_to(.01)
    # A deliberately delayed old capture must not overwrite a newer demand.
    old_demand = dict(request_id="live:1:A:demand_old", owner_id="A", kind="demand",
        target_owner="B", message_delay=0., publication_delay=2.)
    payloads.append(old_demand);session.submit_protocol_command(old_demand)
    session.advance_to(.1)
    submit("demand_new", "demand", target_owner="B")
    submit("middle", "service_forecast", target_owner="B", tray_id="T0", next=1)
    session.advance_to(.2)
    submit("withdraw", "withdraw_service_forecast", forecast_request_id="live:1:A:old")
    submit("latest", "service_forecast", target_owner="B", tray_id="T0", next=1)
    session.advance_to(.3)
    requests = [p["request_id"] for p in payloads]
    checkpoint = session.checkpoint(); branch = session.fork()
    for period in (.01, .1, 1., 100., .1): equivalent(session, requests, period)
    for current in (session, branch):
        for payload in payloads: current.submit_protocol_command(payload)
        current.advance_to(2.2)
        for period in (100., .01, .1, 1.): equivalent(current, requests, period)
    assert session.offline_state_sha256() == branch.offline_state_sha256()
    session.restore(checkpoint)
    equivalent(session, requests)
    # Same-size restore is intentionally not detectable from journal lengths.
    other = native.NativeSession(scene(**protocol));other.advance_to(0.)
    for payload in payloads:
        changed = dict(payload, request_id=payload["request_id"]+"_different")
        other.submit_protocol_command(changed)
    other.advance_to(.3);equivalent(other)
    other.restore(checkpoint)
    assert ordered(equivalent(other, requests)) == ordered(equivalent(session, requests))


def test_legacy_publication_and_receipt_predicate_loading_transit_storage_unloading(native):
    data = tiny_cycle();data["transfers"] = []
    session = native.NativeSession(data)
    for now in (0., .01, .1, 1., 5., 10., 20., 40.):
        session.advance_to(now)
        session.publish_demand("A", "B", 0.)
        session.advance_to(now)
        seal = session.offline_state_sha256()
        session._set_indexed_message_selection(False)
        old = [session.observe(owner) for owner in ("A", "B")]
        session._set_indexed_message_selection(True)
        assert ordered([session.observe(owner) for owner in ("A", "B")]) == ordered(old)
        assert session.offline_state_sha256() == seal


def semantic(value):
    if isinstance(value, dict):
        return {key: semantic(item) for key, item in value.items() if key not in {
            "wall_seconds", "compute_wall_ms", "compute_cpu_ms", "submit_compute_ms", "wall_ms", "cpu_ms"}}
    if isinstance(value, list): return [semantic(item) for item in value]
    return value


@pytest.mark.parametrize("name,data,owners", scenarios())
def test_native_complete_controller_call_boundary_timer_state_and_seal_parity(native, name, data, owners):
    records = []
    for enabled in (False, True):
        value = deepcopy(data);value["owner_notifications"] = {"enabled": True}
        session = native.NativeSession(value);session._set_indexed_message_selection(enabled)
        state = None;parts = []
        for _ in range(1000):
            part = run_event_protocol_control(session, owners, horizon=20., event_budget=100000,
                max_activations=25, state=state, control_period=.5, command_delay=.01,
                publication_delay=.02, retry_period=.5, lease_seconds=120.)
            state = json.loads(json.dumps(part["controller_state"]));parts.append(part)
            if part["status"] != "control_budget_exhausted": break
        assert part["status"] == "reached"
        records.append((ordered(semantic(parts)), session.offline_state_sha256()))
    assert records[0] == records[1], name
