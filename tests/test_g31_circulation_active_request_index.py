"""Derived active-request indexes preserve the full ACK/cooldown state machine."""
from copy import deepcopy
import json
import math
import os

import pytest

from scripts.experiments.g31_ics_circulation.event_protocol_control import _sync_owner_timers, run_event_protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient


class ScriptedEndpoint:
    """Only delivered snapshots are returned, including an explicit lost ACK."""
    def __init__(self):
        self.physical_time = 0.
        self.views = {}
        self.sent = []

    def submit_protocol_command(self, payload):
        self.sent.append(deepcopy(payload))
        return {"status": "rejected" if payload.get("test_reject") else "pending"}

    submit_protocol_transfer = submit_protocol_command

    def protocol_command(self, owner, request_id):
        return deepcopy(self.views.get(request_id, {"request_id": request_id, "status": "pending"}))

    protocol_request = protocol_command


def public_calls(client_or_run):
    calls = client_or_run.calls if isinstance(client_or_run, ProtocolClient) else client_or_run["client_calls"]
    return [{k: v for k, v in row.items() if k != "submit_compute_ms"} for row in calls]


def timers(client):
    state = {"forecasts": {}}
    for owner in ("A", "B"):
        _sync_owner_timers(client, owner, state)
    return state


def delivered(status, at=0.):
    return {"status": "acknowledged", "last_delivered_ack": {"status": status, "delivered_at": at}}


def test_owner_order_pending_ack_loss_rejection_cooldown_and_history_match_full_scan():
    endpoints = [ScriptedEndpoint(), ScriptedEndpoint()]
    clients = [ProtocolClient(endpoint, retry_period=.5, _use_active_request_index=flag)
               for endpoint, flag in zip(endpoints, (False, True))]
    for endpoint, client in zip(endpoints, clients):
        for rid, owner, kind, payload in [
            ("a-done", "A", "demand", {}), ("b-rejected", "B", "demand", {"test_reject": True}),
            ("a-lost", "A", "transfer", {}), ("a-expired", "A", "route", {}),
            ("b-done", "B", "demand", {})]:
            client.submit(owner, kind, payload, request_id=rid)
        endpoint.views.update({"a-done": delivered("delivered"), "a-expired": delivered("expired"),
                               "b-done": delivered("delivered")})
    for now, owner in [(0., "A"), (math.nextafter(.2, -math.inf), "B"), (.2, "A"),
                       (.2, "B"), (.5, None), (.5, None)]:
        results = []
        for endpoint, client in zip(endpoints, clients):
            endpoint.physical_time = now
            results.append(client.refresh(owner_id=owner))
        assert results[0] == results[1]
        assert clients[0].state == clients[1].state
        assert timers(clients[0]) == timers(clients[1])
        assert public_calls(clients[0]) == public_calls(clients[1])
    assert [c["request"]["request_id"] for c in public_calls(clients[1]) if c["retry"]] == ["a-lost"]
    assert list(clients[1].state["outbox"]) == ["a-done", "b-rejected", "a-lost", "a-expired", "b-done"]
    assert clients[1].state["outbox"]["a-expired"]["cooldown_consumed"]
    assert clients[1].state["outbox"]["b-rejected"]["cooldown_consumed"]
    assert not clients[1].state["outbox"]["a-lost"]["terminal"]
    assert timers(clients[1])["timer_live"] == {"retry:a-lost": [1., 1, "A", "transport_retry"]}


@pytest.mark.parametrize("source_index", [False, True])
def test_json_restore_rebuilds_active_indexes_without_mutating_or_shortening_history(source_index):
    endpoint = ScriptedEndpoint()
    source = ProtocolClient(endpoint, retry_period=.5, _use_active_request_index=source_index)
    for i in range(100):
        rid, _ = source.submit("A" if i % 2 else "B", "demand", {}, request_id=str(i))
        endpoint.views[rid] = delivered("delivered")
    source.submit("B", "transfer", {}, request_id="lost")
    source.submit("A", "route", {"test_reject": True}, request_id="cooldown")
    source.refresh()
    saved = json.loads(json.dumps(source.state))
    clone = ProtocolClient(endpoint, retry_period=.5, state=saved, _use_active_request_index=not source_index)
    endpoint.physical_time = .5
    assert source.refresh() == clone.refresh()
    assert source.state == clone.state
    assert len(clone.state["outbox"]) == 102
    assert saved["outbox"]["cooldown"].get("cooldown_consumed") is None
    assert clone.state["outbox"]["cooldown"]["cooldown_consumed"]
    assert public_calls(clone)[0]["request"] == saved["outbox"]["lost"]["payload"]
    assert timers(source) == timers(clone)
    assert not any("index" in key or "active" in key for key in clone.state)


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def scene(protocol=None):
    data = tiny_cycle()
    data["transfers"] = []
    for job in data["jobs"]:
        job["allow_suffix_reroute"] = True
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": 0., **(protocol or {})}
    data["owner_notifications"] = {"enabled": True}
    return data


OPTIONS = dict(control_period=1., command_delay=0., publication_delay=0., retry_period=.5)


def without_timing(rows, fields):
    return [{k: v for k, v in row.items() if k not in fields} for row in rows]


@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 2},
    {"duplicate_acks": True, "duplicate_ack_delay": 0.},
    {"owner_outages": [{"owner": "B", "start": .2, "end": 12.}]}])
def test_native_index_preserves_requests_timers_same_timestamp_boundaries_and_physics(native, protocol):
    a, b = native.NativeSession(scene(protocol)), native.NativeSession(scene(protocol))
    indexed = run_event_protocol_control(a, ["A", "B"], horizon=30., **OPTIONS)
    scanned = run_event_protocol_control(b, ["A", "B"], horizon=30., _use_active_request_index=False, **OPTIONS)
    assert public_calls(indexed) == public_calls(scanned)
    assert without_timing(indexed["control_records"], {"compute_wall_ms", "compute_cpu_ms"}) == without_timing(
        scanned["control_records"], {"compute_wall_ms", "compute_cpu_ms"})
    assert without_timing(indexed["native_batches"], {"wall_ms", "cpu_ms"}) == without_timing(
        scanned["native_batches"], {"wall_ms", "cpu_ms"})
    assert indexed["controller_state"] == scanned["controller_state"]
    assert a.offline_state_sha256() == b.offline_state_sha256()


def test_native_budget_json_resume_can_switch_index_without_losing_cooldown_or_request(native):
    data = scene({"drop_ack_packets": 1})
    full_session = native.NativeSession(data)
    full = run_event_protocol_control(full_session, ["A", "B"], horizon=30.,
        _use_active_request_index=False, **OPTIONS)
    session = native.NativeSession(data)
    combined, state = [], None
    for step in range(2000):
        piece = run_event_protocol_control(session, ["A", "B"], horizon=30., state=state,
            event_budget=1, max_activations=1, _use_active_request_index=bool(step % 2), **OPTIONS)
        combined.extend(public_calls(piece))
        state = json.loads(json.dumps(piece["controller_state"]))
        if piece["status"] == "reached":
            break
        session = session.fork()
    else:
        pytest.fail("budget continuation did not converge")
    assert combined == public_calls(full)
    assert state == full["controller_state"]
    assert session.offline_state_sha256() == full_session.offline_state_sha256()
