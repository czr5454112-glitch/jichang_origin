import pytest
from scripts.experiments.g31_ics_circulation.rolling_request_lineage import RequestLineage


def contract(**changes):
    return {"kind": "one_shot_update", "goal_id": "finite-update", "terminal_failure_allowed": True, **changes}


def ack(identity, status="updated", **changes):
    return {"request_id": identity, "sequence": 1, "status": status, "delivered_at": 1., **changes}


def finish(graph, root, wall, *, disposition="no_action", classified=True):
    graph.seal(root, disposition=disposition, classification_complete=classified, at=1., wall_ns=wall)
    graph.drain(root, timestamp_complete=True, at=1., wall_ns=wall+1)
    graph.output(root, at=1., wall_ns=wall+2)


def begin(graph, root, wall, *, relation="independent_offer", **kw):
    graph.accept(root, scope="owner_activation_proxy", completion_contract=contract(),
                 owner="A", trigger_id="trigger:" + root, trigger_kind="new_message", relation=relation,
                 at=1., wall_ns=wall, **kw)
    graph.observe(root, references=[{"identity": "source-capture", "delivered_at": 1.}], at=1., wall_ns=wall + 1)


def test_missing_ack_processing_or_drain_keeps_complete_duration_unknown():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "intent", {"next": 3}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    with pytest.raises(ValueError, match="output_before_disposition"):
        graph.output("root", at=1., wall_ns=3)
    report = graph.summary("root")
    assert report["elapsed_envelope_ms"] is None and report["status"] == "unknown_incomplete_lineage"
    assert any("terminal_ack" in p for p in report["pending"])


def test_retry_keeps_identity_and_mutated_payload_fails():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "intent", {"next": 3}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    graph.submit("root", "intent", {"next": 3}, required_terminal_statuses=("updated",), retry=True, at=1., wall_ns=3)
    assert len(graph.protocol) == 1 and len(graph.protocol["intent"]["attempts"]) == 2
    with pytest.raises(ValueError, match="retry_identity"):
        graph.submit("root", "intent", {"next": 8}, required_terminal_statuses=("updated",), retry=True, at=1., wall_ns=4)


def test_explicit_continuation_child_extends_parent_without_amortization():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "original", {"next": 3}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    graph.handle_ack("original", ack("original", "rejected"), at=1., wall_ns=3)
    begin(graph, "child", 4, relation="fallback", parents=("root",), predecessor_protocol_id="original")
    graph.submit("child", "replacement", {"next": 8}, required_terminal_statuses=("updated",), at=1., wall_ns=6)
    graph.handle_ack("replacement", ack("replacement"), at=1., wall_ns=10_000_000)
    graph.seal("child", disposition="completed", classification_complete=True, at=1., wall_ns=10_000_001)
    graph.drain("child", timestamp_complete=True, at=1., wall_ns=11_000_000)
    graph.output("child", at=1., wall_ns=12_000_000)
    graph.seal("root", disposition="completed", classification_complete=True, at=1., wall_ns=12_000_001)
    graph.drain("root", timestamp_complete=True, at=1., wall_ns=13_000_000)
    graph.output("root", at=1., wall_ns=14_000_000)
    report = graph.summary("root")
    assert report["closure"] == ["child", "root"] and report["elapsed_envelope_ms"] == 14.
    assert graph.protocol["replacement"]["parent_roots"] == ["child", "root"]
    assert not report["compute_time_measured"] and not report["shared_work_apportionment_measured"]


def test_incidental_read_of_old_reservation_is_independent_not_continuation():
    graph = RequestLineage(); begin(graph, "old", 0)
    finish(graph, "old", 2)
    begin(graph, "new", 100)
    assert graph.summary("old")["closure"] == ["old"]
    assert graph.summary("old")["elapsed_envelope_ms"] == .000004


def test_unclassified_roots_future_inputs_and_undeclared_parents_fail_closed():
    graph = RequestLineage(); begin(graph, "old", 0); begin(graph, "new", 2)
    with pytest.raises(ValueError, match="undeclared_continuation"):
        graph.submit("new", "intent", {}, required_terminal_statuses=("updated",), continuation_parent_roots=("old",), at=1., wall_ns=4)
    finish(graph, "new", 5, classified=False)
    assert graph.summary("new")["elapsed_envelope_ms"] is None
    graph.accept("future", scope="maintenance_update", completion_contract=contract(), owner="A", trigger_id="f", trigger_kind="message", relation="independent_offer", at=1., wall_ns=8)
    with pytest.raises(ValueError, match="future_input"):
        graph.observe("future", references=[{"delivered_at": 2.}], at=1., wall_ns=9)


def test_no_action_drain_cannot_precede_observation_or_final_decision():
    graph = RequestLineage()
    graph.accept("root", scope="owner_activation_proxy", completion_contract=contract(), owner="A", trigger_id="t",
        trigger_kind="tick", relation="independent_offer", at=1., wall_ns=0)
    with pytest.raises(ValueError, match="drain_requires_final_disposition"):
        graph.drain("root", timestamp_complete=True, at=1., wall_ns=1)
    graph.observe("root", references=[], at=1., wall_ns=2)
    with pytest.raises(ValueError, match="drain_requires_final_disposition"):
        graph.drain("root", timestamp_complete=True, at=1., wall_ns=3)
    finish(graph, "root", 3)
    assert graph.summary("root")["status"] == "complete_declared_lineage"


def test_closed_root_cannot_be_reopened_by_later_fallback_or_submission():
    graph = RequestLineage(); begin(graph, "old", 0); finish(graph, "old", 2)
    with pytest.raises(ValueError, match="continuation_after_final_disposition"):
        begin(graph, "late", 5, relation="fallback", parents=("old",))
    with pytest.raises(ValueError, match="submission_outside"):
        graph.submit("old", "late", {}, required_terminal_statuses=("updated",), at=1., wall_ns=6)
    assert graph.summary("old")["status"] == "complete_declared_lineage"


def test_parent_cannot_seal_before_explicit_child_finishes():
    graph = RequestLineage(); begin(graph, "old", 0)
    begin(graph, "child", 2, relation="fallback", parents=("old",))
    with pytest.raises(ValueError, match="seal_before_required_child"):
        graph.seal("old", disposition="completed", classification_complete=True, at=1., wall_ns=4)


def test_duplicate_ack_processing_is_stamped_and_identity_changes_rejected():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "intent", {}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    graph.handle_ack("intent", ack("intent"), at=1., wall_ns=3)
    graph.handle_ack("intent", ack("intent"), at=1., wall_ns=4)
    assert [x["duplicate"] for x in graph.protocol["intent"]["handling_events"]] == [False, True]
    assert graph.protocol["intent"]["handled"]["wall_ns"] == 4
    with pytest.raises(ValueError, match="terminal_ack_identity"):
        graph.handle_ack("intent", ack("intent", sequence=2), at=1., wall_ns=5)
    finish(graph, "root", 5, disposition="completed")
    with pytest.raises(ValueError, match="requires_new_update"):
        graph.handle_ack("intent", ack("intent"), at=1., wall_ns=8)


@pytest.mark.parametrize("at,wall", [(-.5, 0), (0., -1)])
def test_initial_clocks_cannot_be_negative(at, wall):
    with pytest.raises(ValueError, match="noncausal_clock"):
        RequestLineage().accept("x", scope="maintenance_update", completion_contract=contract(), owner="A",
            trigger_id="t", trigger_kind="tick", relation="independent_offer", at=at, wall_ns=wall)


def test_explicit_scope_finite_contract_and_failure_policy_required():
    graph = RequestLineage()
    common = dict(owner="A", trigger_id="t", trigger_kind="tick", relation="independent_offer", at=1., wall_ns=0)
    with pytest.raises(ValueError, match="finite_contract"):
        graph.accept("bad", scope="maintenance_update", completion_contract={"kind": "forever"}, **common)
    with pytest.raises(ValueError, match="task_scope"):
        graph.accept("bad", scope="business_task_update", completion_contract=contract(), **common)
    graph.accept("root", scope="business_task_update", jobs=("real-bag",), completion_contract=contract(terminal_failure_allowed=False), **common)
    graph.observe("root", references=[], at=1., wall_ns=1)
    with pytest.raises(ValueError, match="failure_not_allowed"):
        graph.seal("root", disposition="terminal_failure", classification_complete=True, at=1., wall_ns=2)


def test_rejection_cannot_be_relabelled_completed_without_explicit_replacement():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "intent", {}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    graph.handle_ack("intent", ack("intent", "rejected"), at=1., wall_ns=3)
    with pytest.raises(ValueError, match="failed_operation_without_completed_replacement"):
        graph.seal("root", disposition="completed", classification_complete=True, at=1., wall_ns=4)
    finish(graph, "root", 4, disposition="terminal_failure")
    assert graph.summary("root")["status"] == "complete_declared_lineage"


def test_ack_identity_and_invalid_reference_time_fail_closed():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "intent", {}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    with pytest.raises(ValueError, match="terminal_delivered_ack_required"):
        graph.handle_ack("intent", ack("foreign"), at=1., wall_ns=3)
    graph.accept("other", scope="maintenance_update", completion_contract=contract(), owner="A", trigger_id="t",
        trigger_kind="tick", relation="independent_offer", at=1., wall_ns=4)
    with pytest.raises(ValueError, match="invalid_time"):
        graph.observe("other", references=[{"delivered_at": float("nan")}], at=1., wall_ns=5)


def test_delivery_ack_does_not_satisfy_declared_route_update_goal():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "route", {}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    graph.handle_ack("route", ack("route", "delivered"), at=1., wall_ns=3)
    with pytest.raises(ValueError, match="failed_operation_without_completed_replacement"):
        finish(graph, "root", 4, disposition="completed")


def test_declared_cancellation_goal_can_complete_on_cancelled():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "cancel", {}, required_terminal_statuses=("cancelled",), at=1., wall_ns=2)
    graph.handle_ack("cancel", ack("cancel", "cancelled"), at=1., wall_ns=3)
    finish(graph, "root", 4, disposition="completed")
    assert graph.summary("root")["status"] == "complete_declared_lineage"


def test_retry_cannot_change_required_terminal_operation_contract():
    graph = RequestLineage(); begin(graph, "root", 0)
    graph.submit("root", "route", {}, required_terminal_statuses=("updated",), at=1., wall_ns=2)
    with pytest.raises(ValueError, match="retry_identity"):
        graph.submit("root", "route", {}, required_terminal_statuses=("delivered",), retry=True, at=1., wall_ns=3)
