"""Pure admission and failure-denominator guards for the native rolling driver."""
import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import research_native_rolling_joint as runner


def test_protocol_retains_all_gates_and_same_information_baselines():
    plan = runner.protocol()
    assert len(plan["rows"]) == plan["native_branch_budget"] == 12
    assert {r["gate"] for r in plan["rows"].values()} == {0., 6., 12.}
    assert {r["method"] for r in plan["rows"].values()} == set(runner.METHODS)
    assert all(r["status"] == "unknown_unexecuted" for r in plan["rows"].values())
    assert plan["population_protection"].find("zero tolerance") >= 0


@pytest.mark.parametrize("info", [{}, {"status": "conditional_native_delivered_later_model_input", "native_delivery_verified": False},
    {"status": "conditional_validated_later_data", "native_delivery_verified": True}])
def test_all_methods_withhold_missing_native_input(info):
    for method in runner.METHODS:
        assert runner.choose(info, method)["selected_action"] is None


def test_frozen_later_uses_same_verified_model_input(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.model, "predict", lambda bundle, action: calls.append((bundle, action)) or {"status": "conditional_prediction"})
    value = runner.choose({"status": "conditional_native_delivered_later_model_input", "native_delivery_verified": True,
        "bundle": {"authenticated_test": True}}, "frozen_later")
    assert value["selected_action"] == {"reuse_next": 3, "return_delay": 0.}
    assert calls == [({"authenticated_test": True}, value["selected_action"])]


def test_transport_never_refreshes_foreign_owner_and_retry_keeps_identity():
    class Session:
        physical_time = 1.
        def __init__(self): self.queries = []; self.submits = []
        def submit_protocol_command(self, payload): self.submits.append(copy.deepcopy(payload)); return {"status": "pending"}
        def protocol_command(self, owner, identity): self.queries.append((owner, identity)); return {}
    session = Session(); client = runner.LocalTransport(session)
    client.activate("A", {"kind": "test"}); first = client.submit("A", "demand", "a", target_owner="B")
    client.activate("B", {"kind": "test"}); second = client.submit("B", "demand", "b", target_owner="A")
    session.physical_time = 2.; client.activate("A", {"kind": "timer"}); client.refresh_owner("A")
    assert session.queries == [("A", first)]
    assert session.submits[-1] == session.submits[0]
    assert second not in client.owned("A")
    with pytest.raises(ValueError, match="global_refresh_forbidden"): client.refresh()
    with pytest.raises(ValueError, match="submission_without_owned_admission"): client.submit("B", "demand", "foreign")


def test_rejected_or_missing_branch_keeps_whole_comparison_unknown():
    rows = runner.protocol()["rows"]
    for row in rows.values():
        row.update(status="assessed", summary={"completion": dict.fromkeys(runner.model.JOBS, 1.), "completion_sum": 4.,
            "rolling_model_inputs_verified": True, "rolling_fallback_count": 0})
    rows["gate6/coordinate_strict"]["status"] = "unknown_failed"
    report = runner.assess(rows)
    assert report["6.0"]["status"] == "unknown_incomplete_comparison"
    assert set(report["6.0"]["rows"]) == set(runner.METHODS)


def test_strict_protection_has_no_numeric_tolerance():
    rows = runner.protocol()["rows"]
    for row in rows.values():
        row.update(status="assessed", summary={"completion": dict.fromkeys(runner.model.JOBS, 1.), "completion_sum": 4.,
            "rolling_model_inputs_verified": True, "rolling_fallback_count": 0})
    row = rows["gate6/resource_pair_repair"]
    row["summary"]["completion"]["receiver"] += 1e-12
    row["summary"]["completion_sum"] += 1e-12
    assert runner.assess(rows)["6.0"]["methods"]["resource_pair_repair"]["strict_protected"] is False


def test_collection_wait_and_fallback_are_explicit_without_hidden_advance(monkeypatch):
    session = SimpleNamespace(physical_time=1.08)
    class Client:
        rows = {"own": {"ack": {}}}
        def owned(self, owner): return {}
    policy = runner.OwnerPolicy(None, session, Client(), "A", None, "demand", "coordinate_strict")
    policy.pending = {"phase": "first_return", "at": 1., "deadline": 1.08, "request_id": "own", "root": "accepted", "peer_message": None}
    monkeypatch.setattr(runner.adapter, "collect_native", lambda *a, **k: {"status": "unknown", "native_delivery_verified": False})
    view = {"now": 1.07, "trays": [], "delivered_messages": []}
    policy.decide_pending(view); assert policy.pending is not None and policy.decisions == []
    view["now"] = 1.08; policy.decide_pending(view)
    assert policy.pending is None and policy.decisions[0]["fallback_used"] is True
    assert policy.decisions[0]["native_request_id"] is None
    assert policy.decisions[0]["information"]["native_delivery_verified"] is False


def test_reply_requires_native_source_local_phase_and_never_replies_to_reply():
    envelope = {"schema": "g31.planning_snapshot.v2", "kind": "planning_snapshot_v2", "status": "conditional", "delivered_at": 1.02,
        "capture": {"local_capture": {"source_owner": "A", "target_owner": "B", "captured_at": 1.01, "valid_until": 1.2,
            "trays": [{"tray_id": "L", "edge_to": -1, "node": 6, "mode": "empty", "business_bag_id": "", "available_at": 1.}]}}}
    assert runner.invitation_phase(envelope, "B", 1.03) == "first_return"
    reply = copy.deepcopy(envelope); reply["capture"]["local_capture"].update(source_owner="B", target_owner="A", trays=[])
    assert runner.invitation_phase(reply, "A", 1.03) is None
    assert runner.invitation_phase(envelope, "A", 1.03) is None
    assert runner.invitation_phase(envelope, "B", 1.01) is None
    assert runner.invitation_phase(envelope, "B", 1.21) is None
    envelope["status"] = "expired"
    assert runner.invitation_phase(envelope, "B", 1.03) is None


def test_each_delivered_phase_invitation_answered_once_even_after_no_pending_collection(monkeypatch):
    envelope = {"schema": "g31.planning_snapshot.v2", "kind": "planning_snapshot_v2", "status": "conditional", "delivered_at": 1.02,
        "capture": {"local_capture": {"message_id": "first", "source_owner": "A", "target_owner": "B", "captured_at": 1.01, "valid_until": 1.2,
            "trays": [{"tray_id": "L", "edge_to": -1, "node": 6, "mode": "empty", "business_bag_id": "", "available_at": 1.}]}}}
    session = SimpleNamespace(physical_time=1.03, protocol_planning_snapshots_v2=lambda owner: [envelope])
    policy = runner.OwnerPolicy(None, session, None, "B", None, "demand", "frozen_later")
    calls = []; monkeypatch.setattr(policy, "publication", lambda label, causal: calls.append(causal) or "reply")
    policy.exchange({"now": 1.03}); policy.exchange({"now": 1.03})
    envelope["capture"]["local_capture"]["message_id"] = "fresh_same_phase"
    policy.exchange({"now": 1.04})
    assert len(calls) == 1 and policy.answered_phases == {"first_return"}


def test_selected_peer_revision_cannot_be_replaced_by_newer_or_older_message():
    rows = [{"capture": {"local_capture": {"message_id": identity, "captured_at": at}}}
        for identity, at in (("old", 1.), ("selected", 2.), ("newer", 3.))]
    before = copy.deepcopy(rows)
    assert runner.adapter.selected_received_message(rows, "selected", 2.) == [rows[1]]
    assert runner.adapter.selected_received_message(rows, "selected", 2.1) == []
    assert runner.adapter.selected_received_message(rows, "missing", 2.) == []
    assert runner.adapter.selected_received_message(rows + [rows[1]], "selected", 2.) == []
    assert rows == before


def test_preflight_uses_actual_loading_message_and_immutable_retry_then_delivered_ack(monkeypatch):
    envelope = {"schema": "g31.planning_snapshot.v2", "kind": "planning_snapshot_v2", "status": "conditional", "delivered_at": 1.02,
        "capture": {"local_capture": {"message_id": "loading", "source_owner": "B", "target_owner": "A", "captured_at": 1.01, "valid_until": 1.2,
            "trays": [{"tray_id": "L", "edge_to": -1, "node": 7, "mode": "loading", "business_bag_id": "reuse1",
                "service_ready_known": True, "load_complete_at": 1.1}]}}}
    assert runner.invitation_phase(envelope, "A", 1.02) == "reuse1_loading_ack_refresh"
    row = {"kind": "transfer", "request": {"request_id": "immutable", "owner_id": "A", "tray_id": "L", "source": 6,
        "destination": 7}, "terminal": False, "ack": {"status": "departed", "delivered_at": 1.}}
    sends, publications = [], []
    client = SimpleNamespace(rows={"immutable": row}, owned=lambda owner: {"immutable": row},
        send=lambda identity, retry: sends.append((identity, retry)), creations={"immutable": {"creating_root": "return-root"}})
    session = SimpleNamespace(physical_time=1.02, protocol_planning_snapshots_v2=lambda owner: [envelope])
    policy = runner.OwnerPolicy(None, session, client, "A", None, "demand", "frozen_later")
    monkeypatch.setattr(policy, "publication", lambda label, causal: publications.append(causal) or "reply")
    policy.exchange({"now": 1.02}); policy.exchange({"now": 1.02})
    assert sends == [("immutable", True)] and publications == []
    policy.finish_deferred_reply({"now": 1.04}); assert publications == []
    row["ack"] = {"status": "received", "delivered_at": 1.05}
    policy.finish_deferred_reply({"now": 1.04}); assert publications == []
    policy.finish_deferred_reply({"now": 1.05})
    assert len(publications) == 1 and policy.pending_reply is None
    assert publications[0]["continuation_parent_roots"] == ["return-root"]
    assert publications[0]["delivered_terminal_acknowledgements"]["immutable"] == row["ack"]


def test_loading_preflight_requires_known_future_load_bound():
    local = {"message_id": "loading", "source_owner": "B", "target_owner": "A", "captured_at": 1.01, "valid_until": 1.2,
        "trays": [{"tray_id": "L", "edge_to": -1, "node": 7, "mode": "loading", "business_bag_id": "reuse1",
            "service_ready_known": False, "load_complete_at": 1.1}]}
    value = {"schema": "g31.planning_snapshot.v2", "kind": "planning_snapshot_v2", "status": "conditional", "delivered_at": 1.02,
        "capture": {"local_capture": local}}
    assert runner.invitation_phase(value, "A", 1.02) is None
    local["trays"][0]["service_ready_known"] = True; local["trays"][0]["load_complete_at"] = 1.
    assert runner.invitation_phase(value, "A", 1.02) is None
