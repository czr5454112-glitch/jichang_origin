"""Bound private serialization without changing windows or expiry lifecycles."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import conditional_service_windows
from scripts.experiments.g31_ics_circulation.event_protocol_control import (
    _due_timers, _sync_owner_timers, run_event_protocol_control,
)
from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input, tiny_cycle
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient, _publish_services


def reference_projection(messages, now, validity):
    """Independent specification over already-delivered public dictionaries."""
    candidates = [m for m in messages if m["kind"] == "service_forecast" and m["status"] != "withdrawn"]
    groups = {}
    for message in candidates:
        groups.setdefault((message["source_owner"], message["tray_id"]), []).append(message)
    retained = set()
    for rows in groups.values():
        revision = lambda m: (m["observed_at"], m["generation"], m["publication_sequence"])
        maximum = max(map(revision, rows))
        retained.add((rows[0]["source_owner"], rows[0]["message_id"]))
        retained.update((m["source_owner"], m["message_id"]) for m in rows
                        if revision(m) == maximum or (m["status"] == "conditional" and now < m["observed_at"] + validity))
    return [m for m in messages if m["kind"] != "service_forecast" or
            (m["source_owner"], m["supersedes"] if m["status"] == "withdrawn" else m["message_id"]) in retained]


def message(identity, tray, observed, sequence, *, status="conditional", supersedes=""):
    return dict(kind="service_forecast", message_id=identity, source_owner="A", target_owner="B",
                tray_id=tray, observed_at=observed, delivered_at=observed, generation=1,
                publication_sequence=sequence, status=status, supersedes=supersedes,
                next=1, entry_estimate=20., release_estimate=30.)


class Views:
    def __init__(self, rows, now):
        self.physical_time = now
        self.rows = rows
        self.reads = []

    def observe_protocol_control(self, owner):
        return dict(now=self.physical_time, owner_id=owner, client_transfer_ledger=[],
                    trays=[], jobs=[], node_records=[], edge_records=[], node_contracts=[],
                    edge_contracts=[], known_faults=[], delivered_messages=deepcopy(self.rows))

    observe_protocol = observe_protocol_control

    def observe_protocol_control_policy(self, owner):
        self.reads.append("policy")
        return self.observe_protocol_control(owner)

    def observe_protocol_control_policy_recent(self, owner, validity):
        self.reads.append(("recent", validity))
        result = self.observe_protocol_control(owner)
        result["delivered_messages"] = reference_projection(result["delivered_messages"], result["now"], validity)
        return result


def timers(client, view):
    state = {"forecasts": {}}
    _publish_services(client, "B", state, command_delay=.01, publication_delay=.02,
                      routes=False, forecasts=False, lease_seconds=1., observation=view)
    _sync_owner_timers(client, "B", state)
    return state


@pytest.mark.parametrize("now,validity", [(1.5, 1.), (2., 1.), (2.1, 1.), (20., 100.), (20., .01)])
def test_projection_preserves_window_order_all_revision_timers_and_json_restore(now, validity):
    rows = [message("first-X", "X", 0., 1), message("first-Y", "Y", .1, 2),
            message("middle-X", "X", .2, 3), message("latest-Y", "Y", 1., 4),
            message("latest-X", "X", 1.1, 5),
            message("withdraw-old-X", "X", 1.2, 6, status="withdrawn", supersedes="middle-X")]
    session = Views(rows, now)
    full = ProtocolClient(session, forecast_validity=validity, _use_recent_forecasts=False)
    recent = ProtocolClient(session, forecast_validity=validity)
    a, b = full._policy_view("B"), recent._policy_view("B")
    assert conditional_service_windows(a) == conditional_service_windows(b)
    left, right = timers(full, a), timers(recent, b)
    assert json.dumps(left) == json.dumps(right)
    deadline = now + validity + 2.
    assert _due_timers(left, deadline) == _due_timers(json.loads(json.dumps(right)), deadline)
    assert full.state == recent.state


def test_withdrawal_before_original_and_expired_latest_never_resurrect_old_revision():
    original = message("original", "X", 0., 1)
    withdrawal = message("withdraw", "X", .2, 2, status="withdrawn", supersedes="original")
    latest = message("latest", "X", .5, 3)
    for rows, now in [([withdrawal], .3), ([original, withdrawal], .3),
                      ([original, withdrawal, latest], .6), ([original, withdrawal, latest], 1.5)]:
        session = Views(rows, now)
        a = ProtocolClient(session, forecast_validity=1., _use_recent_forecasts=False)._policy_view("B")
        b = ProtocolClient(session, forecast_validity=1.)._policy_view("B")
        assert conditional_service_windows(a) == conditional_service_windows(b)
        assert timers(ProtocolClient(session, forecast_validity=1.), a) == timers(ProtocolClient(session, forecast_validity=1.), b)
    assert conditional_service_windows(b) == []


def test_runtime_option_public_view_and_proxy_fallback_do_not_change_checkpoint():
    session = Views([message("one", "X", 0., 1)], 2.)
    client = ProtocolClient(session, forecast_validity=.5)
    saved = deepcopy(client.state)
    client._policy_view("B")
    assert session.reads[-1] == ("recent", .5)
    assert client.view("B") == client._policy_view("B", compact=False)
    restored = ProtocolClient(session, forecast_validity=.5, state=json.loads(json.dumps(saved)), _use_recent_forecasts=False)
    restored._policy_view("B")
    assert session.reads[-1] == "policy" and restored.state == saved == client.state
    class ForwardingProxy:
        def __getattr__(self, name):
            return getattr(session, name)
    count = len(session.reads)
    ProtocolClient(ForwardingProxy(), forecast_validity=.5)._policy_view("B")
    assert len(session.reads) == count


@pytest.fixture(scope="module")
def native():
    module = load_native(os.environ["G31_CIRCULATION_BINARY"])
    assert hasattr(module.NativeSession, "observe_protocol_control_policy_recent")
    return module


def scene(**protocol):
    data = tiny_cycle()
    data["transfers"] = []
    data["jobs"] = [dict(data["jobs"][0], load_seconds=30., allow_suffix_reroute=True)]
    next(n for n in data["node_contracts"] if n["node"] == 1)["resource_owner"] = "B"
    data["owner_protocol"] = {"enabled": True, "timeout": .4, "ack_delay": .02, **protocol}
    data["owner_notifications"] = {"enabled": True}
    return prepare_input(data)


def compare_native_views(session, validity):
    before = session.offline_state_sha256()
    full = session.observe_protocol_control_policy("B")
    recent = session.observe_protocol_control_policy_recent("B", validity)
    expected = deepcopy(full)
    expected["delivered_messages"] = reference_projection(full["delivered_messages"], full["now"], validity)
    assert json.dumps(recent) == json.dumps(expected)
    a = ProtocolClient(session, forecast_validity=validity, _use_recent_forecasts=False)._policy_view("B")
    b = ProtocolClient(session, forecast_validity=validity)._policy_view("B")
    assert conditional_service_windows(a) == conditional_service_windows(b)
    assert timers(ProtocolClient(session, forecast_validity=validity), a) == timers(ProtocolClient(session, forecast_validity=validity), b)
    recent["delivered_messages"].clear()
    assert session.observe_protocol_control_policy("B") == full
    assert session.offline_state_sha256() == before


def test_native_late_original_withdrawals_expiry_and_restore_recompute_exact_projection(native):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    def publish(name, delay=0.):
        payload = dict(request_id="live:1:A:"+name, owner_id="A", kind="service_forecast",
                       target_owner="B", tray_id="T0", next=1, publication_delay=delay)
        session.submit_protocol_command(payload)
    publish("old", 2.)
    session.advance_to(.1)
    publish("second")
    session.advance_to(.2)
    session.submit_protocol_command(dict(request_id="live:1:A:withdraw", owner_id="A",
        kind="withdraw_service_forecast", forecast_request_id="live:1:A:old"))
    session.advance_to(.3)
    publish("third")
    session.advance_to(.4)
    publish("fourth")
    session.advance_to(.5)
    checkpoint = session.checkpoint()
    fork = session.fork()
    for validity in (.1, 1., 100.):
        compare_native_views(session, validity)
    session.advance_to(2.1)
    for validity in (.1, 1., 100.):
        compare_native_views(session, validity)
    session.restore(checkpoint)
    assert session.observe_protocol_control_policy_recent("B", 1.) == fork.observe_protocol_control_policy_recent("B", 1.)
    for current in (session, fork):
        current.advance_to(2.1)
    assert session.offline_state_sha256() == fork.offline_state_sha256()
    assert session.observe_protocol_control_policy_recent("B", 100.) == fork.observe_protocol_control_policy_recent("B", 100.)


@pytest.mark.parametrize("validity", [0., -1., float("inf"), float("nan")])
def test_native_explicit_validity_is_required_and_invalid_period_does_not_mutate(native, validity):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    before = session.offline_state_sha256()
    with pytest.raises((TypeError, ValueError)):
        session.observe_protocol_control_policy_recent("B")
    with pytest.raises(ValueError, match="invalid_forecast_validity"):
        session.observe_protocol_control_policy_recent("B", validity)
    assert session.offline_state_sha256() == before


def without_times(value):
    if isinstance(value, dict):
        return {k: without_times(v) for k, v in value.items() if k not in {
            "wall_seconds", "submit_compute_ms", "compute_wall_ms", "compute_cpu_ms", "wall_ms", "cpu_ms"}}
    if isinstance(value, list):
        return [without_times(v) for v in value]
    return value


@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 1, "duplicate_acks": True, "duplicate_ack_delay": .001},
    {"owner_outages": [{"owner": "A", "start": .5, "end": 2.5}]}])
def test_native_controller_full_tape_and_checkpoint_equivalence(native, protocol):
    options = dict(control_period=1000., retry_period=.7, command_delay=.01, publication_delay=.02,
        forecast_refresh_period=.6, forecast_validity=1., rejection_cooldown=.3,
        forecast_change_threshold=.5, prebalance=False, routes=False)
    runs, seals = [], []
    for enabled in (False, True):
        session = native.NativeSession(scene(**protocol))
        first = run_event_protocol_control(session, ["A", "B"], horizon=4., max_activations=17,
            _use_recent_forecasts=enabled, **options)
        state = json.loads(json.dumps(first["controller_state"]))
        second = run_event_protocol_control(session, ["A", "B"], horizon=4., state=state,
            _use_recent_forecasts=enabled, **options)
        runs.append(without_times([first, second]))
        seals.append(session.offline_state_sha256())
    assert runs[0] == runs[1] and seals[0] == seals[1]
