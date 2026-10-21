"""Pure public-data/controller gates; no native session is constructed."""
from copy import deepcopy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as r0
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as joint
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_control as control
from scripts.experiments.g31_ics_circulation import foundation_airport_protocol_v2 as controller
from scripts.experiments.g31_ics_circulation import protocol_control as protocol
from test_g31_airport_inventory_rule import observation, tray, PublicSession, TickSession


def prepare(current):
    prepared = joint.prepare_current(current, r0.r0_priority_planner(current))
    return prepared, joint.build_joint_catalog(prepared)


def two_sources():
    current = observation()
    current["static_role_contract"]["loader_nodes"] = [2]
    current["trays"].append(tray("near", 1))
    current["node_contracts"][1].update(actual_available=1, occupancy=1)
    current["node_records"] = [(0, 10, .001, 0, 0, [2]),
        (1, 10, .001, 0, 0, [2]), (2, 10, .001, 0, 0, [])]
    current["edge_records"] = [(0, 2, 100., 1.), (1, 2, 2., 1.)]
    current["edge_contracts"] = [{"from": source, "to": 2, "capacity": 10} for source in (0, 1)]
    return current


def test_joint_bridge_replaces_source_id_bias_with_cross_source_eta():
    current = two_sources()
    assert r0.select_stock_return(current)["intents"][0]["source"] == 0
    prepared, catalog = prepare(current)
    choice = control.select_joint_bridge(prepared, catalog)
    assert control.apply_selected_action(prepared, catalog, choice)["intents"][0]["source"] == 1
    assert catalog["candidate_source_node_count"] == catalog["candidate_source_tray_count"] == 2


def test_reference_and_alternative_different_trays_each_have_one_move():
    prepared, catalog = prepare(two_sources())
    actions = catalog["candidates"][1:]
    reference = control.apply_selected_action(prepared, catalog, actions[0]["action_id"])
    alternative = control.apply_selected_action(prepared, catalog, actions[1]["action_id"])
    assert [len(row["intents"]) for row in (reference, alternative)] == [1, 1]
    assert reference["intents"][0]["tray_id"] != alternative["intents"][0]["tray_id"]
    assert prepared.baseline["intents"] == []
    assert control.apply_selected_action(prepared, catalog, "a_noop")["intents"] == []


def test_new_menu_nonzero_target_is_legal_while_bridge_holds():
    current = observation(source=1, stock=2)
    current["node_contracts"][2].update(actual_available=1, occupancy=1)
    current["trays"].append(tray("target", 2))
    prepared, catalog = prepare(current)
    moves = catalog["candidates"][1:]
    assert moves and all(row["source"] == 1 and row["destination"] == 2 for row in moves)
    assert all(not row["bridge_eligible"] for row in moves)
    assert control.select_joint_bridge(prepared, catalog)["action_id"] == "a_noop"


def test_fifo_minimum_and_pledged_trays_remain_protected():
    current = observation(source=1, stock=3)
    current["node_contracts"][1]["export_min_stock"] = 1
    current["jobs"] = [{"business_bag_id": "local", "origin": 1, "arrival": 1.,
        "status": "waiting_for_tray"}]
    prepared, catalog = prepare(current)
    assert {row["tray_id"] for row in catalog["candidates"][1:]} == {"E2"}
    current["client_transfer_ledger"] = [{"request_id": "held", "tray_id": "E2",
        "source": 1, "destination": 2, "status": "granted"}]
    _, catalog = prepare(current)
    assert catalog["K"] == 1


def test_loader_singleton_and_real_priority_cannot_enter_optional_menu():
    _, catalog = prepare(observation(source=1, stock=1))
    assert catalog["K"] == 1
    current = observation()
    current["jobs"] = [{"business_bag_id": "waiting", "origin": 1, "arrival": 1.,
        "status": "waiting_for_tray"}]
    with pytest.raises(ValueError, match="priority_intents_remain"):
        prepare(current)


def test_unknown_inventory_is_not_zero_and_no_forecast_enters_catalog():
    current = observation(source=1, stock=2, remote=True)
    prepared, catalog = prepare(current)
    assert catalog["candidates"][1]["destination_actual_empty"] is None
    assert catalog["candidates"][1]["destination_inventory_known"] is False
    assert control.select_joint_bridge(prepared, catalog)["action_id"] == "a_noop"
    with pytest.raises(ValueError, match="unknown_catalog_config"):
        joint.build_joint_catalog(prepared, {"forecast": {"future": 100}})


@pytest.mark.parametrize("mutation,reason", [
    (lambda p, c: p.observation.update(version=20), "stale_public_state"),
    (lambda p, c: p.baseline.update(policy="different"), "changed_priority_baseline"),
    (lambda p, c: c["candidates"][1]["intent"].update(tray_id="forged"), "catalog_changed")])
def test_stale_and_tampered_prepared_catalog_are_rejected(mutation, reason):
    prepared, catalog = prepare(two_sources())
    mutation(prepared, catalog)
    with pytest.raises(ValueError, match=reason):
        control.apply_selected_action(prepared, catalog, catalog["candidates"][1]["action_id"])


def test_bridge_keeps_ordinary_return_category_before_optional_loader():
    current = two_sources()
    current["static_role_contract"]["loader_nodes"] = [1, 2]
    current["trays"].append(tray("near2", 1))
    current["node_contracts"][1].update(actual_available=2, occupancy=2)
    prepared, catalog = prepare(current)
    choice = control.select_joint_bridge(prepared, catalog)
    result = control.apply_selected_action(prepared, catalog, choice)
    assert result["intents"][0]["source"] == 0


def post(client, state, **options):
    return protocol._post_inventory_return(client, "A", state, compact=True,
        command_delay=1., priority_error=False,
        stock_return_selector=options.pop("selector", control.JointPostPrioritySelector()),
        stock_return_selector_identity="joint-test-v1", **options)


@pytest.mark.parametrize("failure", ["rejected", "exception"])
def test_quota_is_consumed_before_rejection_or_exception_and_survives_json(failure):
    session = PublicSession()
    def fail(payload):
        session.transfer_calls.append(deepcopy(payload))
        if failure == "exception":
            raise RuntimeError("transport_exception")
        return {"status": "rejected"}
    session.submit_protocol_transfer = fail
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {"next_tick": 4}
    if failure == "exception":
        with pytest.raises(RuntimeError, match="transport_exception"):
            post(client, state)
    else:
        assert post(client, state)["attempts"][0]["reply"]["status"] == "rejected"
    restored = json.loads(json.dumps(state))
    assert post(client, restored)["reason"] == "owner_tick_return_quota_spent"
    assert len(session.transfer_calls) == 1
    assert restored["joint_post_priority"]["policy_state"]["decision_count"] == 1


def test_noop_is_observed_once_per_versioned_decision_and_new_ticks_continue():
    session = PublicSession()
    session.current = observation(source=1, stock=1)
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state, observed = {"next_tick": 1}, []
    opts = {"post_decision_observer": lambda **kw: observed.append(kw["decision"])}
    assert post(client, state, **opts)["decision"]["intents"] == []
    assert post(client, state, **opts)["reason"] == "same_post_priority_decision_already_recorded"
    state = json.loads(json.dumps(state)); state["next_tick"] = 2
    post(client, state, **opts)
    assert len(observed) == 2
    assert state["joint_post_priority"]["policy_state"]["decision_count"] == 2
    assert not session.transfer_calls


def test_protocol_retry_keeps_original_request_id_without_spending_second_quota():
    session = PublicSession()
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {"next_tick": 1}
    result = post(client, state)
    identity = result["attempts"][0]["request_id"]
    session.physical_time += 2.
    client.refresh()
    assert len(session.transfer_calls) == 2
    assert all(row["request_id"] == identity for row in session.transfer_calls)
    assert state["inventory_return_quota"]["A"]["new_submissions"] == 1


def test_submission_exception_restores_outbox_poll_and_retry_under_same_identity():
    session = PublicSession()
    original_submit = session.submit_protocol_transfer
    def first_submit(payload):
        session.transfer_calls.append(deepcopy(payload))
        raise RuntimeError("lost_submission_reply")
    session.submit_protocol_transfer = first_submit
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {"next_tick": 1}
    with pytest.raises(RuntimeError, match="lost_submission_reply"):
        post(client, state)
    original_request = session.transfer_calls[0]
    saved = json.loads(json.dumps(client.state))
    client = protocol.ProtocolClient(session, inventory_snapshots=True, state=saved)
    session.submit_protocol_transfer = original_submit
    session.physical_time += 2.
    client.refresh()
    assert len(session.transfer_calls) == 2
    assert session.transfer_calls[1] == original_request
    assert post(client, state)["reason"] == "owner_tick_return_quota_spent"


def test_policy_exception_before_any_submission_does_not_spend_attempt_quota():
    session = PublicSession()
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {"next_tick": 1}
    def unavailable(*args, **kwargs):
        raise RuntimeError("model_unavailable")
    with pytest.raises(RuntimeError, match="model_unavailable"):
        post(client, state, selector=control.JointPostPrioritySelector(unavailable))
    assert state["inventory_return_quota"]["A"]["new_submissions"] == 0
    assert not session.transfer_calls


def test_recording_sink_cannot_change_the_selected_physical_move():
    current = observation()
    def corrupt(**kwargs):
        kwargs["decision"]["intents"][0]["destination"] = 2
    selector = control.JointPostPrioritySelector(decision_sink=corrupt)
    with pytest.raises(ValueError, match="decision_sink_modified_selection"):
        selector(current, r0.r0_priority_planner(current), message_delay=0.,
            request_prefix="test", policy_state={}, decision_context={"tick": 0})


def test_controller_checkpoint_binds_selector_and_preserves_noop_policy_state(monkeypatch):
    session = TickSession()
    session.priority = []
    session.current = observation(source=1, stock=1)
    monkeypatch.setattr(controller, "_publish_services", lambda *a, **kw: [])
    options = dict(predictive=False, forecasts=False, routes=False, inventory_snapshots=True,
        stock_return=True, stock_return_selector=control.JointPostPrioritySelector(),
        stock_return_selector_identity="joint-test-v1", control_period=1.)
    initial = controller.run_airport_bounded_protocol_control(session, ["A"], horizon=0., **options)
    saved = json.loads(json.dumps(initial["controller_state"]))
    continued = controller.run_airport_bounded_protocol_control(session, ["A"], horizon=1., state=saved, **options)
    assert continued["controller_state"]["joint_post_priority"]["policy_state"]["decision_count"] == 2
    assert continued["controller_state"]["config"]["post_priority_control_contract"] == control.CONTROL_CONTRACT
    with pytest.raises(ValueError, match="state_configuration_mismatch"):
        controller.run_airport_bounded_protocol_control(session, ["A"], horizon=1., state=continued["controller_state"],
            **{**options, "stock_return_selector_identity": "changed-policy"})
