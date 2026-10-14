"""Public A* codec and delayed regional intents on real G31 continuations."""
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.regional_control import (
    complete_on_demand, decode_route, encode_route, make_route_packet, public_astar, submit_on_demand,
)


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def scene():
    data = tiny_cycle()
    data["transfers"] = []
    data["jobs"][0]["allow_suffix_reroute"] = True
    return data


def test_codec_preserves_actual_prefix_and_storage_obligation(native):
    s = native.NativeSession(scene())
    s.advance_to(1.16)
    observation = s.observe("A")
    packet = make_route_packet(observation, "T0")
    assert packet.committed_prefix == (0, 1)
    assert packet.stage_goal == 2 and packet.stage == "storage_in"
    assert packet.replaceable_suffix == (1, 2)
    assert decode_route(encode_route(packet)) == packet
    with pytest.raises(ValueError, match="prefix_or_stage_mismatch"):
        encode_route(replace(packet, committed_prefix=(0, 6)))
    with pytest.raises(ValueError, match="prefix_or_stage_mismatch"):
        encode_route(replace(packet, stage_goal=4))


def test_astar_excludes_closed_and_advertised_edges_without_remote_queues(native):
    s = native.NativeSession(scene()); s.advance_to(.11)
    observation = s.observe("A")
    assert all("occupancy" not in n for n in observation["node_contracts"] if n["resource_owner"] != "A")
    assert public_astar(observation, 0, 2) == (0, 1, 2)
    closed = deepcopy(observation)
    next(e for e in closed["edge_contracts"] if (e["from"], e["to"]) == (0, 1))["capacity"] = 0
    assert public_astar(closed, 0, 2) == (0, 6, 2)
    closed["known_faults"] = [{"from": 0, "to": 6, "active": True}]
    assert public_astar(closed, 0, 2) == ()


@pytest.mark.parametrize("delay,expected", [(0.01, "allowed"), (0.2, "stale_executed_prefix")])
def test_on_demand_request_has_actual_completion_and_stale_rejection(native, delay, expected):
    data = scene(); s = native.NativeSession(data); s.advance_to(.11)
    receipt = submit_on_demand(s, "A", "T0", "on-demand", logical_compute_delay=delay)
    assert receipt["response"]["status"] == "pending"
    assert not receipt["complete_100ms_requirement_certified"]
    assert receipt["submission_compute_ms"] >= 0
    result = s.result_at(30)
    request = s.observe("A")["route_requests"][0]
    assert request["reason"] == expected
    audit_result(data, result)
    assert result["jobs"][0]["status"] == "completed"


def test_on_demand_policy_cannot_skip_permission_or_committed_edge(native):
    data = scene(); data["jobs"][0]["allow_suffix_reroute"] = False
    s = native.NativeSession(data); s.advance_to(.11)
    receipt = submit_on_demand(s, "A", "T0", "not-authorized")
    assert receipt["response"]["reason"] == "route:service_obligation_disallows_reroute"
    assert not s.observe("A")["route_requests"]
    s.advance_to(.2)
    receipt = submit_on_demand(s, "A", "T0", "entered")
    assert receipt["response"]["reason"] == "route:committed_edge_cannot_be_replaced"


def test_future_tape_cannot_change_regional_packet(native):
    first = scene(); first["jobs"][1]["arrival"] = 50
    other = deepcopy(first); other["jobs"][1]["arrival"] = 60
    other["faults"] = [{"from": 0, "to": 1, "start": 40, "end": 45}]
    a = native.NativeSession(first); b = native.NativeSession(other)
    a.advance_to(.11); b.advance_to(.11)
    assert make_route_packet(a.observe("A"), "T0") == make_route_packet(b.observe("A"), "T0")


@pytest.mark.parametrize("delay,reason", [(.01,"allowed"), (.2,"stale_executed_prefix")])
def test_complete_compute_measurement_includes_actual_delivered_owner_response(native,delay,reason):
    s=native.NativeSession(scene());s.advance_to(.11)
    measured=complete_on_demand(s,"A","T0","complete-chain",message_delay=delay)
    assert measured["final_response"]["reason"]==reason
    assert measured["physical_finished_at"]==pytest.approx(.11+delay)
    assert measured["compute_wall_ms"]>=measured["submission"]["submission_compute_ms"]
    assert not measured["hard_realtime_guarantee"]
    assert not measured["complete_100ms_requirement_certified"]


def test_compute_event_budget_keeps_unknown_in_denominator(native):
    s=native.NativeSession(scene());s.advance_to(.11)
    measured=complete_on_demand(s,"A","T0","bounded-chain",message_delay=10,event_budget=1)
    assert measured["final_response"]["status"]=="timeout_unknown"
    assert measured["advance"]["status"]=="budget_exhausted"
    assert s.physical_time<10.11
