"""LT2 C2: public timer lifecycle on the actual native016 owner protocol."""
from copy import deepcopy
import json
import math
import os

import pytest

from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input, tiny_cycle
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def scene(*, loaded=False, protocol=None):
    data = tiny_cycle()
    data["transfers"] = []
    data["jobs"] = [dict(data["jobs"][0], load_seconds=0. if loaded else 30., allow_suffix_reroute=True)]
    if loaded:
        data["node_records"] = [(n, kind, 30. if n == 0 else service, x, y, outgoing)
            for n, kind, service, x, y, outgoing in data["node_records"]]
    next(n for n in data["node_contracts"] if n["node"] == 1)["resource_owner"] = "B"
    data["owner_protocol"] = {"enabled": True, "timeout": .4, "ack_delay": .02, **(protocol or {})}
    data["owner_notifications"] = {"enabled": True}
    return prepare_input(data)


OPTIONS = dict(control_period=1000., retry_period=.7, command_delay=.01, publication_delay=.02,
    forecast_refresh_period=2., forecast_validity=3., rejection_cooldown=.3,
    forecast_change_threshold=.5, prebalance=False, routes=False)


def fresh(run, kind):
    return [c for c in run["client_calls"] if c["kind"] == kind and not c["retry"]]


def calls(run):
    return [{k: v for k, v in c.items() if k != "submit_compute_ms"} for c in run["client_calls"]]


def test_same_stage_success_refreshes_without_periodic_ticks_or_message_flood(native):
    session = native.NativeSession(scene(protocol={"duplicate_acks": True, "duplicate_ack_delay": .001}))
    run = run_event_protocol_control(session, ["A", "B"], horizon=6.5, **OPTIONS)
    assert run["status"] == "reached"
    publications = fresh(run, "service_forecast")
    assert 3 <= len(publications) <= 4
    assert publications[0]["at"] == 0.
    assert all(b["at"]-a["at"] >= 2. for a, b in zip(publications, publications[1:]))
    assert len(fresh(run, "withdraw_service_forecast")) == len(publications)-1
    assert all(r["causes"].get("periodic_tick", 0) == 0 for r in run["control_records"])
    assert any(t["kind"] == "forecast_refresh_or_expiry" for r in run["control_records"] for t in r["causes"].get("timers", []))
    assert session.observe_protocol("A")["trays"][0]["mode"] == "loading"
    assert len({json.loads(key.split("]:")[0]+"]")[3] for key in run["controller_state"]["forecasts"]}) == 1


def test_expiry_withdraws_and_receiver_refuses_expired_estimate(native):
    data = scene(protocol={"owner_outages": [{"owner": "A", "start": .5, "end": 10.}]})
    session = native.NativeSession(data)
    options = dict(OPTIONS, forecast_refresh_period=20., forecast_validity=1.)
    run = run_event_protocol_control(session, ["A", "B"], horizon=1.8, **options)
    assert run["status"] == "reached"
    withdrawals = fresh(run, "withdraw_service_forecast")
    assert withdrawals and withdrawals[0]["at"] == 1.01
    client = ProtocolClient(session, forecast_validity=1.)
    messages = [m for m in client.view("B")["delivered_messages"] if m["kind"] == "service_forecast"]
    assert messages and all(m["status"] == "expired" for m in messages)
    assert any(t["kind"] == "received_forecast_expiry" for r in run["control_records"] if r["owner_id"] == "B" for t in r["causes"].get("timers", []))


class RejectOneSubmission:
    """Explicit test fault injection; all accepted commands execute natively."""
    def __init__(self, session, kind):
        self.session, self.kind, self.rejected = session, kind, False

    def __getattr__(self, name):
        return getattr(self.session, name)

    def submit_protocol_command(self, payload):
        if payload["kind"] == self.kind and not self.rejected:
            self.rejected = True
            return {"status": "rejected", "reason": "test_injected_submission_rejection"}
        return self.session.submit_protocol_command(payload)


def test_injected_rejected_withdrawal_retries_as_new_intent_then_native_delivery(native):
    session = RejectOneSubmission(native.NativeSession(scene()), "withdraw_service_forecast")
    run = run_event_protocol_control(session, ["A", "B"], horizon=4., **OPTIONS)
    withdrawals = fresh(run, "withdraw_service_forecast")
    assert len(withdrawals) >= 2
    rows = run["controller_state"]["client"]["outbox"]
    statuses = [rows[c["request"]["request_id"]].get("client_view", {}).get("last_delivered_ack", rows[c["request"]["request_id"]]["submission_reply"]).get("status") for c in withdrawals]
    assert "rejected" in statuses and "delivered" in statuses
    assert len({c["request"]["forecast_request_id"] for c in withdrawals}) == 1
    assert len(fresh(run, "service_forecast")) == 2
    assert any(t["kind"] == "rejection_cooldown" for r in run["control_records"] for t in r["causes"].get("timers", []))


def test_route_lease_is_active_timer_without_periodic_tick(native):
    session = native.NativeSession(scene(loaded=True))
    run = run_event_protocol_control(session, ["A", "B"], horizon=3.2,
        **dict(OPTIONS, forecasts=False, routes=True, lease_seconds=1.))
    routes = fresh(run, "route")
    assert [c["at"] for c in routes] == [0., 1., 2., 3.]
    assert len({c["request"]["expected_generation"] for c in routes}) == 1
    assert any(t["kind"] == "route_lease" for r in run["control_records"] for t in r["causes"].get("timers", []))


@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 2},
    {"duplicate_acks": True, "duplicate_ack_delay": .001},
    {"owner_outages": [{"owner": "A", "start": 1.9, "end": 3.}]}])
def test_timer_heap_and_dedup_generations_checkpoint_equivalence(native, protocol):
    data = scene(protocol=protocol)
    continuous = native.NativeSession(data)
    full = run_event_protocol_control(continuous, ["A", "B"], horizon=7., **OPTIONS)
    split = native.NativeSession(data)
    prefix = run_event_protocol_control(split, ["A", "B"], horizon=2.03, **OPTIONS)
    saved = json.loads(json.dumps(prefix["controller_state"], allow_nan=False))
    before = deepcopy(saved)
    resumed_native = native.NativeSession(data)
    resumed_native.restore(split.checkpoint())
    resumed = run_event_protocol_control(resumed_native, ["A", "B"], horizon=7., state=saved, **OPTIONS)
    assert saved == before
    assert calls(prefix)+calls(resumed) == calls(full)
    assert resumed["controller_state"] == full["controller_state"]
    assert resumed_native.offline_state_sha256() == continuous.offline_state_sha256()
    assert saved["timer_heap"] and saved["timer_generations"]


def test_timer_nextafter_boundary_is_strict(native):
    session = native.NativeSession(scene())
    before = math.nextafter(2., -math.inf)
    prefix = run_event_protocol_control(session, ["A", "B"], horizon=before, **OPTIONS)
    assert not fresh(prefix, "withdraw_service_forecast")
    at = run_event_protocol_control(session, ["A", "B"], horizon=2., state=prefix["controller_state"], **OPTIONS)
    assert fresh(at, "withdraw_service_forecast")[0]["at"] == 2.


def test_native_zero_delay_work_drains_between_owner_activations(native):
    session = native.NativeSession(scene(protocol={"ack_delay": 0.}))
    run = run_event_protocol_control(session, ["A", "B"], horizon=.1,
        **dict(OPTIONS, command_delay=0., publication_delay=0.))
    trace = sorted([*run["control_records"], *run["native_batches"]], key=lambda r: r["trace_sequence"])
    for left, right in zip(trace, trace[1:]):
        assert not ("owner_epoch" in left and "owner_epoch" in right)
    assert all(b["timestamp_complete"] for b in run["native_batches"])


def test_terminal_demand_rejection_cooldown_fires_without_periodic_tick(native):
    session = RejectOneSubmission(native.NativeSession(scene()), "demand")
    run = run_event_protocol_control(session, ["A", "B"], horizon=.5,
        **dict(OPTIONS, forecasts=False))
    publications = [c for c in fresh(run, "demand") if c["request"]["owner_id"] == "A"]
    assert [c["at"] for c in publications] == [0., .3]
    assert publications[0]["reply"]["status"] == "rejected"
    assert publications[1]["reply"]["status"] == "pending"
    assert publications[0]["request"]["request_id"] != publications[1]["request"]["request_id"]


def test_delivered_fault_condition_signature_survives_json_checkpoint(native):
    data = scene()
    # A delivered local fault is present in the signature in both branches;
    # tuples silently converted by JSON must not invent a condition change.
    data["faults"] = [{"from": 0, "to": 6, "start": .2, "end": 10., "message_delay": 0.}]
    continuous = native.NativeSession(data)
    full = run_event_protocol_control(continuous, ["A", "B"], horizon=5., **OPTIONS)
    split = native.NativeSession(data)
    prefix = run_event_protocol_control(split, ["A", "B"], horizon=.5, **OPTIONS)
    state = json.loads(json.dumps(prefix["controller_state"]))
    resumed = run_event_protocol_control(split, ["A", "B"], horizon=5., state=state, **OPTIONS)
    assert calls(prefix)+calls(resumed) == calls(full)
    assert resumed["controller_state"] == full["controller_state"]
    assert split.offline_state_sha256() == continuous.offline_state_sha256()
