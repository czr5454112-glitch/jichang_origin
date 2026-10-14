"""Actual native notifications, legal owner activation and budget continuation."""
from copy import deepcopy
import json
import math
import os

import pytest

from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control
from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, prepare_input, tiny_cycle
from scripts.experiments.g31_ics_circulation.validate_protocol_control import replay_input
from scripts.experiments.g31_ics_circulation.validate_event_protocol_control import assess_synthetic


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def scene(changes=None):
    data = tiny_cycle()
    data["transfers"] = []
    for job in data["jobs"]:
        job["allow_suffix_reroute"] = True
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02, **(changes or {})}
    data["owner_notifications"] = {"enabled": True}
    return data


OPTIONS = dict(control_period=1., command_delay=.01, publication_delay=.02, retry_period=.5)


def calls(run):
    return [{k: v for k, v in row.items() if k != "submit_compute_ms"} for row in run["client_calls"]]


@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 1},
    {"duplicate_acks": True, "duplicate_ack_delay": .1},
    {"owner_outages": [{"owner": "B", "start": .2, "end": 12.}]}])
def test_event_controller_native_checkpoint_json_continuation(native, protocol):
    data = scene(protocol)
    continuous = native.NativeSession(data)
    full = run_event_protocol_control(continuous, ["A", "B"], horizon=30., **OPTIONS)
    split = native.NativeSession(data)
    prefix = run_event_protocol_control(split, ["A", "B"], horizon=7.37, **OPTIONS)
    assert prefix["status"] == "reached"
    saved = split.checkpoint()
    parent_hash = split.offline_state_sha256()
    state = json.loads(json.dumps(prefix["controller_state"], allow_nan=False))
    sibling = native.NativeSession(data)
    sibling.restore(saved)
    before = deepcopy(state)
    resumed = run_event_protocol_control(sibling, ["A", "B"], horizon=30., state=state, **OPTIONS)
    assert state == before
    assert resumed["status"] == full["status"] == "reached"
    for key in ("jobs", "trays", "transfers", "receipts", "leg_identities"):
        assert resumed["result"][key] == full["result"][key], key
    assert resumed["controller_state"] == full["controller_state"]
    assert calls(prefix) + calls(resumed) == calls(full)
    assert continuous.offline_state_sha256() == sibling.offline_state_sha256()
    assert split.offline_state_sha256() == parent_hash
    assert audit_result(replay_input(data, full["client_calls"]), full["result"])["status"] == "passed"


@pytest.mark.parametrize("event_budget,activation_budget", [(1, 10000), (100000, 1), (1, 1)])
def test_partial_native_or_owner_budget_resumes_without_advancing_to_audit(native, event_budget, activation_budget):
    data = scene({"drop_ack_packets": 1})
    continuous = native.NativeSession(data)
    full = run_event_protocol_control(continuous, ["A", "B"], horizon=30., **OPTIONS)
    split = native.NativeSession(data)
    state, all_calls, partials = None, [], []
    for _ in range(2000):
        run = run_event_protocol_control(split, ["A", "B"], horizon=30., state=state,
            event_budget=event_budget, max_activations=activation_budget, **OPTIONS)
        all_calls.extend(calls(run))
        state = json.loads(json.dumps(run["controller_state"], allow_nan=False))
        if run["status"] == "reached":
            break
        assert run["result"] is None
        assert run["status"] in {"native_budget_exhausted", "control_budget_exhausted"}
        if run["status"] == "native_budget_exhausted":
            assert not state["native_timestamp_complete"]
            assert not state["pending_owners"]
        partials.append(split.physical_time)
        # A real native checkpoint and a JSON controller must suffice even at
        # an interrupted native timestamp or between two owner's actions.
        split = split.fork()
    else:
        pytest.fail("bounded continuation did not converge")
    assert partials and min(partials) < 30.
    assert all_calls == calls(full)
    assert state == full["controller_state"]
    assert split.offline_state_sha256() == continuous.offline_state_sha256()


def test_zero_delay_feedback_drains_whole_timestamp_and_reuses_actual_tray(native):
    data = scene({"ack_delay": 0., "duplicate_acks": True, "duplicate_ack_delay": 0.})
    session = native.NativeSession(data)
    run = run_event_protocol_control(session, ["A", "B"], horizon=30., command_delay=0.,
        publication_delay=0., control_period=60., retry_period=1.)
    assert run["status"] == "reached"
    assert all(job["status"] == "completed" for job in run["result"]["jobs"])
    assert len(run["result"]["transfers"]) == 1
    assert run["result"]["transfers"][0]["status"] == "received"
    assert audit_result(replay_input(data, run["client_calls"]), run["result"])["status"] == "passed"
    assert all(row["timestamp_complete"] for row in run["native_batches"])


def test_owner_budget_after_zero_delay_submit_does_not_claim_complete_native_timestamp(native):
    session = native.NativeSession(scene({"ack_delay": 0.}))
    run = run_event_protocol_control(session, ["A", "B"], horizon=1.,
        command_delay=0., publication_delay=0., max_activations=1)
    assert run["status"] == "control_budget_exhausted"
    assert run["controller_state"]["pending_owners"] == ["B"]
    with pytest.raises(ValueError, match="notification_timestamp_incomplete"):
        session.owner_notifications(["A", "B"])
    assert not run["controller_state"]["native_timestamp_complete"]
    assessed = assess_synthetic(scene(), run, session, 1.)
    assert assessed["status"] == "unknown_incomplete_execution"
    assert assessed["metrics"] is None


def test_private_third_owner_events_cannot_activate_or_refresh_other_clients(native):
    base = scene()
    base["node_records"] += [(7, 1, .05, 7, 0, [8]), (8, 1, .05, 8, 0, [7])]
    base["edge_records"] += [(7, 8, .1, 1.), (8, 7, .1, 1.)]
    base["node_contracts"] += [{"node": n, "zone": "C", "capacity": 1} for n in (7, 8)]
    base["edge_contracts"] += [{"from": u, "to": v, "capacity": 1, "entry_headway": .01} for u, v in ((7, 8), (8, 7))]
    base["trays"].append({"tray_id": "TC", "node": 7})
    base["jobs"].append({"business_bag_id": "PRIVATE_C", "origin": 7, "destination": 8,
        "arrival": .3, "deadline": 20., "load_seconds": .1, "unload_seconds": .1, "hold_seconds": .1})
    base = prepare_input(base)
    other = deepcopy(base)
    other["jobs"][-1]["arrival"] = .7
    runs = [run_event_protocol_control(native.NativeSession(world), ["A", "B", "C"],
        horizon=1., command_delay=2., publication_delay=.5, control_period=60.) for world in (base, other)]
    for owner in ("A", "B"):
        own_calls = lambda run: [row for row in calls(run) if row["request"]["owner_id"] == owner]
        activations = lambda run: [(row["at"], row["causes"]) for row in run["control_records"] if row["owner_id"] == owner]
        assert own_calls(runs[0]) == own_calls(runs[1])
        assert activations(runs[0]) == activations(runs[1])


def test_nextafter_horizon_and_invalid_resume_do_not_cross_future_tick(native):
    session = native.NativeSession(scene())
    before = math.nextafter(1., -math.inf)
    prefix = run_event_protocol_control(session, ["A", "B"], horizon=before, **OPTIONS)
    assert session.physical_time == before
    assert not any(row["at"] >= 1. for row in prefix["control_records"])
    sealed = session.offline_state_sha256()
    with pytest.raises(ValueError, match="invalid_horizon"):
        run_event_protocol_control(session, ["A", "B"], horizon=0., state=prefix["controller_state"], **OPTIONS)
    assert session.offline_state_sha256() == sealed
    resumed = run_event_protocol_control(session, ["A", "B"], horizon=1., state=prefix["controller_state"], **OPTIONS)
    assert sum(row["causes"].get("periodic_tick") == 1 for row in resumed["control_records"]) == 2
