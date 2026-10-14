"""Actual G31 R1/R2 client semantics, native+controller continuation and faults."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.protocol_control import (
    ProtocolClient, complete_protocol_route, run_protocol_control,
)
from scripts.experiments.g31_ics_circulation import protocol_control
from scripts.experiments.g31_ics_circulation.probe_protocol_controller import execute as execute_lifecycle_probes


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def scene(protocol=None):
    data = tiny_cycle()
    data["transfers"] = []
    for job in data["jobs"]:
        job["allow_suffix_reroute"] = True
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02, **(protocol or {})}
    return data


@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 1},
    {"duplicate_acks": True, "duplicate_ack_delay": .1},
    {"owner_outages": [{"owner": "B", "start": .2, "end": 12.}]}])
def test_native_and_json_client_continue_same_full_physics(native, protocol):
    data = scene(protocol)
    continuous = native.NativeSession(data); continuous.advance_to(.11)
    full = run_protocol_control(continuous, ["A", "B"], horizon=30.)
    split = native.NativeSession(data); split.advance_to(.11)
    prefix = run_protocol_control(split, ["A", "B"], horizon=7.37)
    assert prefix["status"] == "reached"
    saved = split.checkpoint()
    parent_hash = split.offline_state_sha256()
    json_state = json.loads(json.dumps(prefix["controller_state"], allow_nan=False))
    sibling = native.NativeSession(data); sibling.restore(saved)
    before = deepcopy(json_state)
    resumed = run_protocol_control(sibling, ["A", "B"], horizon=30., state=json_state)
    assert json_state == before
    assert resumed["status"] == full["status"] == "reached"
    for key in ("jobs", "trays", "transfers", "receipts", "leg_identities"):
        assert resumed["result"][key] == full["result"][key], key
    assert resumed["controller_state"] == full["controller_state"]
    assert continuous.offline_state_sha256() == sibling.offline_state_sha256()
    assert split.offline_state_sha256() == parent_hash


def test_ack_loss_retry_keeps_one_physical_transfer_and_two_real_services(native):
    session = native.NativeSession(scene({"drop_ack_packets": 1}))
    session.advance_to(.11)
    run = run_protocol_control(session, ["A", "B"], horizon=30.)
    assert run["status"] == "reached"
    assert all(j["status"] == "completed" for j in run["result"]["jobs"])
    transfers = run["result"]["transfers"]
    assert len(transfers) == 1 and transfers[0]["status"] == "received"
    calls = [c for c in run["client_calls"] if c["kind"] == "transfer"]
    assert len(calls) > 1
    assert len({c["request"]["request_id"] for c in calls}) == 1
    assert len([r for r in run["result"]["receipts"] if r["event"] == "EXPORT_GRANTED"]) == 1


@pytest.mark.parametrize("delay,reason", [(.01, "allowed"), (.2, "stale_executed_prefix")])
def test_complete_route_uses_delivered_ack_and_counts_full_simulation_work(native, delay, reason):
    session = native.NativeSession(scene({"drop_ack_packets": 1}))
    session.advance_to(.11)
    measured = complete_protocol_route(session, "A", "T0", "live:1:A:complete-query", command_delay=delay)
    assert measured["response"]["reason"] == reason
    assert measured["response"]["delivered_at"] <= session.physical_time
    assert sum(c["retry"] for c in measured["client_calls"]) >= 1
    assert measured["compute_wall_ms"] >= sum(c["submit_compute_ms"] for c in measured["client_calls"])
    assert not measured["complete_100ms_requirement_certified"]


def test_no_delivered_ack_retains_unknown_and_saved_immutable_payload(native):
    session = native.NativeSession(scene({"drop_ack_packets": 100}))
    session.advance_to(.11)
    measured = complete_protocol_route(session, "A", "T0", "live:1:A:no-ack", confirmation_window=.3)
    assert measured["response"]["status"] == "timeout_unknown"
    outbox = measured["client_state"]["outbox"]["live:1:A:no-ack"]
    assert not outbox["terminal"]
    assert len({json.dumps(c["request"], sort_keys=True) for c in measured["client_calls"]}) == 1


def test_future_tape_cannot_change_public_request_payloads(native):
    data = scene(); data["jobs"][1]["arrival"] = 50.
    other = deepcopy(data); other["jobs"][1]["arrival"] = 60.
    other["faults"] = [{"from": 0, "to": 1, "start": 40., "end": 45.}]
    runs = []
    for world in (data, other):
        session = native.NativeSession(world); session.advance_to(.11)
        runs.append(run_protocol_control(session, ["A", "B"], horizon=1.))
    strip = lambda run: [{k: v for k, v in c.items() if k != "submit_compute_ms"} for c in run["client_calls"]]
    assert strip(runs[0]) == strip(runs[1])
    assert runs[0]["controller_state"] == runs[1]["controller_state"]


def test_budget_cut_is_not_complete_and_partial_controller_state_is_not_resumable(native):
    session = native.NativeSession(scene()); session.advance_to(.11)
    result = run_protocol_control(session, ["A", "B"], horizon=30., event_budget=1)
    assert result["status"] == "budget_exhausted"
    assert result["result"] is None
    assert not result["controller_state"]["control_boundary_complete"]
    with pytest.raises(ValueError, match="partial_tick_resume_not_supported"):
        run_protocol_control(session, ["A", "B"], horizon=30., state=result["controller_state"])


def test_restored_client_retry_does_not_mutate_parent_outbox(native):
    session = native.NativeSession(scene()); session.advance_to(.11)
    client = ProtocolClient(session, retry_period=.1)
    client.submit("A", "demand", {"target_owner": "B", "message_delay": 0., "publication_delay": .5})
    saved = deepcopy(client.state)
    branch = session.fork(); branch.advance_to(.31)
    restored = ProtocolClient(branch, retry_period=.1, state=saved)
    restored.refresh()
    assert client.state == saved
    assert restored.state != saved


def test_true_budget_stop_and_same_stage_fault_recovery(native, tmp_path):
    rows = execute_lifecycle_probes(protocol_control, native, tmp_path)
    assert len(rows) == 3 and all(row["fixed"] for row in rows), rows


def test_old_submission_signature_cache_state_cannot_be_restored_as_capture_knowledge(native):
    session = native.NativeSession(scene()); session.advance_to(.11)
    prefix = run_protocol_control(session, ["A", "B"], horizon=.11)
    legacy = deepcopy(prefix["controller_state"])
    legacy["schema"] = "g31.protocol_controller_state.v1"
    legacy["published"] = {owner: session.protocol_demand_signature(owner) for owner in ["A", "B"]}
    before = session.offline_state_sha256()
    with pytest.raises(ValueError, match="state_configuration_mismatch"):
        run_protocol_control(session, ["A", "B"], horizon=30., state=legacy)
    assert session.offline_state_sha256() == before
