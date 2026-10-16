"""Actual ProtocolClient integration over a deterministic public endpoint fake."""
import copy
import itertools
import pytest

from scripts.experiments.g31_ics_circulation.business_update_outbox import BusinessUpdateOutbox
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient


class Session:
    physical_time = 1.
    def __init__(self):
        self.sent, self.acks = [], {}
        self.reject = False
        self.complete = True
        self.reads = 0
    def observe_protocol_control(self, owner):
        self.reads += 1
        return {"owner_id": owner, "client_transfer_ledger": [], "delivered_messages": [], "jobs": [{"business_bag_id": "job1"}]}
    def submit_protocol_command(self, payload):
        self.sent.append(copy.deepcopy(payload))
        return {"status": "rejected" if self.reject else "pending"}
    submit_protocol_transfer = submit_protocol_command
    def protocol_command(self, owner, identity):
        result = {"request_id": identity, "status": "acknowledged"}
        if identity in self.acks: result["last_delivered_ack"] = self.acks[identity]
        return result
    protocol_request = protocol_command
    def advance_to(self, at, max_events):
        assert at == self.physical_time
        return {"status": "reached" if self.complete else "budget_exhausted",
            "horizon_complete": self.complete, "physical_time": at}


def make():
    session = Session()
    client = ProtocolClient(session, retry_period=1.)
    bridge = BusinessUpdateOutbox(client, "A", clock=itertools.count(100).__next__)
    return session, client, bridge


def admit(bridge, root="root", **changes):
    bridge.admit(root, business_job_id="job1", trigger_id="message1:"+root, trigger_kind="delivered_message",
        completion_contract={"kind": "one_shot_update", "goal_id": "install_authorized_decision",
            "terminal_failure_allowed": True}, **changes)
    return bridge.observe(root)


def ack(session, identity, status):
    session.acks[identity] = {"sequence": 1, "status": status, "delivered_at": session.physical_time}


def finish(bridge, root="root", disposition="completed"):
    return bridge.finish(root, {"decision": "returned"}, disposition=disposition,
        classification_complete=True, event_budget=100)


def test_admission_precedes_actual_public_observation_and_installed_route_ack_closes():
    session, client, bridge = make()
    bridge.admit("root", business_job_id="job1", trigger_id="arrival", trigger_kind="local_job",
        completion_contract={"kind": "one_shot_update", "goal_id": "route_install", "terminal_failure_allowed": False})
    assert session.reads == 0
    bridge.observe("root")
    identity, _ = bridge.submit("root", "route", {"business_bag_id": "job1", "next_node": 2}, required_terminal_statuses=("updated",))
    assert bridge.lineage.protocol[identity]["payload_sha256"]
    ack(session, identity, "updated"); bridge.refresh()
    assert finish(bridge)["status"] == "returned"
    report = bridge.report("root")
    assert report["status"] == "complete_declared_lineage"
    assert not report["original_user_contract_accepted"] and not report["compute_time_measured"]
    assert client.state["outbox"][identity]["payload"] == session.sent[0]


def test_lost_ack_retries_same_actual_outbox_identity_and_payload():
    session, client, bridge = make(); admit(bridge)
    identity, _ = bridge.submit("root", "transfer", {"tray_id": "E"}, required_terminal_statuses=("received",))
    session.physical_time = 2.; bridge.refresh()
    assert session.sent[0] == session.sent[1]
    assert len(bridge.lineage.protocol[identity]["attempts"]) == 2
    ack(session, identity, "dispatching"); bridge.refresh()
    with pytest.raises(ValueError, match="seal_before_terminal_handling"): finish(bridge)
    ack(session, identity, "received"); bridge.refresh()
    assert finish(bridge)["status"] == "returned"
    assert len(client.state["outbox"]) == 1


def test_wrong_terminal_status_is_not_success_and_direct_rejection_is_not_delivered_ack():
    session, _, bridge = make(); admit(bridge)
    identity, _ = bridge.submit("root", "route", {"business_bag_id": "job1"}, required_terminal_statuses=("updated",))
    ack(session, identity, "delivered"); bridge.refresh()
    with pytest.raises(ValueError, match="failed_operation_without_completed_replacement"): finish(bridge)
    session, _, bridge = make(); admit(bridge); session.reject = True
    bridge.submit("root", "route", {"business_bag_id": "job1"}, required_terminal_statuses=("updated",))
    bridge.refresh()
    with pytest.raises(ValueError, match="seal_before_terminal_handling"): finish(bridge, disposition="terminal_failure")


def test_no_action_requires_complete_actual_drain_and_keeps_budget_cut_open():
    session, _, bridge = make(); admit(bridge)
    session.complete = False
    result = finish(bridge, disposition="no_action")
    assert result["output"] is None and bridge.report("root")["status"] == "unknown_incomplete_lineage"
    session.complete = True
    assert finish(bridge, disposition="no_action")["status"] == "returned"
    assert bridge.report("root")["status"] == "complete_declared_lineage"


def test_explicit_replacement_child_closes_parent_and_independent_read_does_not():
    session, _, bridge = make(); admit(bridge)
    identity, _ = bridge.submit("root", "route", {"business_bag_id": "job1"}, required_terminal_statuses=("updated",))
    ack(session, identity, "rejected"); bridge.refresh()
    admit(bridge, "independent"); finish(bridge, "independent", "no_action")
    assert bridge.report("root")["closure"] == ["root"]
    admit(bridge, "fallback", relation="fallback", parents=("root",), predecessor_protocol_id=identity)
    replacement, _ = bridge.submit("fallback", "route", {"business_bag_id": "job1", "next": 8}, required_terminal_statuses=("updated",))
    ack(session, replacement, "updated"); bridge.refresh()
    finish(bridge, "fallback"); finish(bridge)
    assert bridge.report("root")["closure"] == ["fallback", "root"]


def test_external_client_activity_and_payload_mutation_fail_closed():
    _, client, bridge = make(); admit(bridge)
    client.submit("A", "route", {"business_bag_id": "job1"})
    with pytest.raises(ValueError, match="unclassified_external_client_activity"): bridge.refresh()
    _, client, bridge = make(); admit(bridge)
    identity, _ = bridge.submit("root", "route", {"business_bag_id": "job1"}, required_terminal_statuses=("updated",))
    client.state["outbox"][identity]["payload"]["next"] = 99
    with pytest.raises(ValueError, match="immutable_outbox_changed"): bridge.refresh()


def test_cancellation_uses_its_explicit_cancelled_contract():
    session, _, bridge = make(); admit(bridge)
    identity, _ = bridge.submit("root", "cancel_transfer", {"reference_request_id": "old"},
        required_terminal_statuses=("cancelled",))
    ack(session, identity, "cancelled"); bridge.refresh()
    assert finish(bridge)["status"] == "returned"


@pytest.mark.parametrize("endpoint", ["observe_protocol_control", "protocol_command"])
def test_failed_actual_read_cannot_be_reclassified_as_successful_no_action(endpoint):
    session, _, bridge = make()
    def fail(*args): raise RuntimeError("read failed")
    if endpoint == "observe_protocol_control":
        session.observe_protocol_control = fail
        with pytest.raises(RuntimeError, match="read failed"): admit(bridge)
    else:
        admit(bridge)
        bridge.submit("root", "route", {"business_bag_id": "job1"}, required_terminal_statuses=("updated",))
        session.protocol_command = fail
        with pytest.raises(RuntimeError, match="read failed"): bridge.refresh()
    with pytest.raises(ValueError, match="prior_unresolved_capture_error"): finish(bridge, disposition="no_action")
    assert bridge.report("root")["status"] == "unknown_incomplete_lineage"


def test_route_job_scope_mismatch_rejected_before_any_outbox_side_effect():
    session, client, bridge = make(); admit(bridge)
    with pytest.raises(ValueError, match="route_job_does_not_match_admission"):
        bridge.submit("root", "route", {"business_bag_id": "job2"}, required_terminal_statuses=("updated",))
    assert client.state["outbox"] == {} and session.sent == []


def test_missing_observed_job_rejects_route_and_no_action_is_label_only():
    session, client, bridge = make()
    session.observe_protocol_control = lambda owner: {"owner_id": owner, "client_transfer_ledger": [], "delivered_messages": []}
    admit(bridge)
    with pytest.raises(ValueError, match="admitted_route_job_not_observed"):
        bridge.submit("root", "route", {"business_bag_id": "job1"}, required_terminal_statuses=("updated",))
    assert not client.state["outbox"]
    finish(bridge, disposition="no_action")
    report = bridge.report("root")
    assert report["job_scope_verified"] is False
    assert report["status"] == "complete_declared_operation_lineage_job_scope_unverified"


def test_transfer_completion_does_not_prove_affected_job_authority():
    session, _, bridge = make(); admit(bridge)
    identity, _ = bridge.submit("root", "transfer", {"tray_id": "E"}, required_terminal_statuses=("received",))
    ack(session, identity, "received"); bridge.refresh(); finish(bridge)
    report = bridge.report("root")
    assert report["status"] == "complete_declared_operation_lineage_job_scope_unverified"
    assert report["job_scope"] == "declared_label_only" and not report["job_scope_verified"]


def test_fallback_cannot_satisfy_a_different_jobs_update():
    _, _, bridge = make(); admit(bridge)
    with pytest.raises(ValueError, match="continuation_job_scope_changed"):
        bridge.admit("wrong", business_job_id="job2", trigger_id="fallback", trigger_kind="rejected_ack",
            completion_contract={"kind": "one_shot_update", "goal_id": "replacement", "terminal_failure_allowed": True},
            relation="fallback", parents=("root",))
