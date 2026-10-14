"""Batch command projection is identical to independently queried client views."""
from copy import deepcopy
import os
from pathlib import Path

import pytest
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary=os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary=next((Path(__file__).resolve().parents[1]/"build_lt_session_016/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def scene(**faults):
    value=tiny_cycle();value["transfers"]=[]
    value["owner_protocol"]={"enabled":True,"ack_delay":.1,"timeout":.05,**faults}
    return value


def commands(session):
    submitted={"A":[],"B":[]}
    for i in range(36):
        owner="A" if i%2 else "B"
        request={"request_id":f"live:1:{owner}:serialization:{i}","owner_id":owner,
            "kind":"demand","target_owner":"B" if owner=="A" else "A",
            "message_delay":(i%3)*.2,"publication_delay":.1}
        if i%5==0:
            request.update(kind="service_forecast",tray_id="missing-tray",next=1)
        assert session.submit_protocol_command(request)["status"]=="pending"
        submitted[owner].append(request)
    return submitted


def check(session, submitted):
    before=session.offline_state_sha256()
    for owner, requests in submitted.items():
        expected=[session.protocol_command(owner,r["request_id"]) for r in requests]
        assert session.observe_protocol(owner)["client_commands"]==expected
        assert session.observe_protocol_control(owner)["client_commands"]==expected
        alien="B" if owner=="A" else "A"
        assert all(session.protocol_command(alien,r["request_id"])["status"]=="unknown_request" for r in requests)
    assert session.offline_state_sha256()==before


@pytest.mark.parametrize("faults", [{},{"drop_ack_packets":1},
    {"duplicate_acks":True,"duplicate_ack_delay":.03},
    {"owner_outages":[{"owner":"A","start":.1,"end":.7}]}])
def test_batch_query_preserves_pending_timeout_ack_drop_duplicate_and_outage(native,faults):
    s=native.NativeSession(scene(**faults));submitted=commands(s)
    for when in (0.,.06,.25,.5,.9):
        assert s.advance_to(when)["horizon_complete"]
        check(s,submitted)
    for requests in submitted.values():
        for request in requests:
            assert s.submit_protocol_command(request)["status"]=="pending"
    s.advance_to(2.)
    check(s,submitted)
    branch=s.fork();check(branch,submitted)
    assert s.offline_state_sha256()==branch.offline_state_sha256()


def test_batch_projection_returns_fresh_nested_ack_dicts_after_checkpoint_restore(native):
    s=native.NativeSession(scene());submitted=commands(s);s.advance_to(2.)
    checkpoint=s.checkpoint();baseline=deepcopy(s.observe_protocol_control("A"))
    changed=s.observe_protocol_control("A")
    for row in changed["client_commands"]:
        row["status"]="user-mutated"
        if "last_delivered_ack" in row:
            row["last_delivered_ack"]["status"]="user-mutated"
            row["last_delivered_ack"].get("captured_demand_signature",{})["sha256"]="user-mutated"
    assert s.observe_protocol_control("A")==baseline
    s.restore(checkpoint)
    assert s.observe_protocol_control("A")==baseline
    check(s,submitted)
