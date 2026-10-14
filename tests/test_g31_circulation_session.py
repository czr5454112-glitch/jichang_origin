"""Actual native continuations and policy-visible information boundaries."""
from copy import deepcopy
import os
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle, audit_result


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def request(now=10):
    return dict(request_id="live:online-1",owner_id="B",tray_id="T0",source=4,destination=0,
                earliest_departure=now,expiry=60,message_delay=0)


def without_return():
    data=tiny_cycle();data["transfers"]=[];return data


@pytest.mark.parametrize("boundary", [.05,.12,1.2,3,6,8.2,9,10,14])
def test_live_restore_is_same_continuation(native,boundary):
    data=tiny_cycle();a=native.NativeSession(data);a.advance_to(boundary)
    checkpoint=a.checkpoint();b=native.NativeSession(data);b.restore(checkpoint)
    assert a.offline_state_sha256()==b.offline_state_sha256()
    ar=a.result_at(70);br=b.result_at(70)
    for key in ["receipts","jobs","trays","transfers","population"]: assert ar[key]==br[key]
    assert a.offline_state_sha256()==b.offline_state_sha256()
    audit_result(data,ar)


def test_quiescent_siblings_diverge_only_after_explicit_action(native):
    data=without_return();parent=native.NativeSession(data);parent.advance_to(10)
    before=parent.offline_state_sha256();a=parent.fork();b=parent.fork()
    assert a.submit_transfer_intent(request())["status"]=="pending"
    assert b.offline_state_sha256()==before==parent.offline_state_sha256()
    ar=a.result_at(70);br=b.result_at(70)
    assert ar["jobs"][1]["status"]=="completed"
    assert br["jobs"][1]["status"]=="waiting_for_tray"
    replay=deepcopy(data);r=request();r.pop("owner_id");r["issued_at"]=10;replay["transfers"].append(r)
    audit_result(replay,ar);audit_result(data,br)


def test_future_environment_never_changes_current_observation(native):
    first=without_return();first["jobs"][1]["arrival"]=50
    second=deepcopy(first);second["jobs"][1]["arrival"]=60
    second["jobs"].append(dict(second["jobs"][1],business_bag_id="unpublished",arrival=70))
    second["faults"]=[{"from":0,"to":1,"start":40,"end":45}]
    a=native.NativeSession(first);b=native.NativeSession(second)
    for t in [0,.11,1,3,8,12]:
        a.advance_to(t);b.advance_to(t)
        for owner in ["A","B"]: assert a.observe(owner)==b.observe(owner)


def test_delayed_demand_is_an_immutable_observed_snapshot(native):
    s=native.NativeSession(without_return());s.advance_to(.25)
    assert s.publish_demand("A","B",1)["status"]=="pending"
    assert s.observe("B")["delivered_messages"]==[]
    snapshot=s.checkpoint();s.advance_to(1.25)
    msg=s.observe("B")["delivered_messages"][0]
    assert msg["observed_at"]==.25 and msg["delivered_at"]==1.25
    assert [j["business_bag_id"] for j in msg["jobs"]]==["B2"]
    msg["jobs"].clear()
    assert s.observe("B")["delivered_messages"][0]["jobs"]
    branch=native.NativeSession(without_return());branch.restore(snapshot);branch.advance_to(1.25)
    assert branch.observe("B")==s.observe("B")


def route_request(observation, delay=.01):
    t=next(t for t in observation["trays"] if t["tray_id"]=="T0")
    return dict(request_id="route-1",owner_id="A",business_bag_id="B1",tray_id="T0",
                **{"from":0,"next":6}, expected_generation=t["generation"],
                expected_traversal=t["traversal_id"],expiry=2,message_delay=delay)


@pytest.mark.parametrize("permission,delay,reason", [(True,.01,"allowed"),(False,.01,"service_obligation_disallows_reroute"),(True,.2,"stale_executed_prefix")])
def test_asynchronous_route_request_obeys_prefix_and_service_permission(native,permission,delay,reason):
    data=without_return();data["jobs"][0]["allow_suffix_reroute"]=permission
    s=native.NativeSession(data);s.advance_to(.11)
    assert s.submit_route_intent(route_request(s.observe("A"),delay))["status"]=="pending"
    result=s.result_at(30)
    requests=s.observe("A")["route_requests"]
    assert requests[0]["reason"]==reason
    first=next(r for r in result["receipts"] if r["event"]=="EDGE_ENTER")
    assert first["to"]==(6 if reason=="allowed" else 1)
    audit_result(data,result)


def test_transfer_permission_staleness_and_cancellation(native):
    s=native.NativeSession(without_return());s.advance_to(10)
    wrong=request();wrong["owner_id"]="A"
    assert s.submit_transfer_intent(wrong)==dict(status="rejected",reason="resource_owner_mismatch")
    stale=request();stale["expected_version"]=999999
    assert s.submit_transfer_intent(stale)["reason"]=="stale_observation"
    assert s.submit_transfer_intent(request())["status"]=="pending"
    assert s.cancel_transfer_intent("live:online-1","A")["status"]=="rejected"
    assert s.cancel_transfer_intent("live:online-1","B")["status"]=="cancelled"
    assert s.result_at(70)["jobs"][1]["status"]=="waiting_for_tray"


def test_committed_empty_prefix_cannot_be_cancelled(native):
    s=native.NativeSession(without_return());s.advance_to(10);s.submit_transfer_intent(request());s.advance_to(10.1)
    assert s.cancel_transfer_intent("live:online-1","B")["reason"]=="already_committed"
    assert s.result_at(70)["jobs"][1]["status"]=="completed"


def test_closed_edge_is_preserved_and_never_entered(native):
    data=tiny_cycle();data["edge_contracts"][0]["capacity"]=0
    result=native.run(data)
    assert all(not(r["event"]=="EDGE_ENTER" and (r["from"],r["to"])==(0,1)) for r in result["receipts"])
    assert all(j["status"]=="completed" for j in result["jobs"])
    audit_result(data,result)


def test_event_budget_does_not_jump_over_unprocessed_physics(native):
    s=native.NativeSession(tiny_cycle());r=s.advance_to(70,max_events=1)
    assert r["status"]=="budget_exhausted" and s.physical_time<70
    assert s.result_at(70)["jobs"][1]["status"]=="completed"


def test_failed_empty_attempt_recovers_with_new_authority_without_erasing_history(native):
    data=tiny_cycle();data["transfers"][0]["expiry"]=11
    data["faults"]=[{"from":4,"to":5,"start":0.,"end":30.,"message_delay":4.}]
    s=native.NativeSession(data);s.advance_to(12)
    assert s.observe("B")["trays"][0]["mode"]=="quarantined"
    assert s.recover_empty_tray("recover-1","A","T0")["status"]=="rejected"
    assert s.recover_empty_tray("recover-1","B","T0",.5)["status"]=="pending"
    branch=s.fork();s.advance_to(12.5);branch.advance_to(12.5)
    assert s.offline_state_sha256()==branch.offline_state_sha256()
    assert s.observe("B")["trays"][0]["mode"]=="empty"
    s.advance_to(34)
    new=request(34);new["request_id"]="live:fresh-after-repair"
    assert s.submit_transfer_intent(new)["status"]=="pending"
    result=s.result_at(75)
    assert result["transfers"][0]["status"]=="failed"
    assert result["transfers"][1]["status"]=="received"
    assert all(j["status"]=="completed" for j in result["jobs"])
    replay=deepcopy(data);new.pop("owner_id");new["issued_at"]=34;replay["transfers"].append(new)
    audit_result(replay,result)


@pytest.mark.parametrize("blocker,reason", [("static_suffix", "no_static_legal_suffix"),
                                           ("notified_fault", "advertised_fault")])
def test_route_update_cannot_claim_a_known_invalid_old_or_new_route(native, blocker, reason):
    data = without_return()
    data["jobs"][0].update(allow_suffix_reroute=True, deadline=-1)
    if blocker == "static_suffix":
        for edge in data["edge_contracts"]:
            if edge["from"] == 6:
                edge["capacity"] = 0
    else:
        data["faults"] = [{"from": 0, "to": 6, "start": 0., "end": 20., "message_delay": 0.}]
    s = native.NativeSession(data); s.advance_to(.11)
    assert s.submit_route_intent(route_request(s.observe("A")))["status"] == "pending"
    result = s.result_at(30)
    reply = s.observe("A")["route_requests"][0]
    assert reply["status"] == "rejected" and reply["reason"] == reason
    assert next(r for r in result["receipts"] if r["event"] == "EDGE_ENTER")["to"] == 1
    audit_result(data, result)
