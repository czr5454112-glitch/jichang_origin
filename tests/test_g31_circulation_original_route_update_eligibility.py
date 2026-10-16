"""Pure scheduling/authority/trace guards, with no native session."""
from copy import deepcopy
import ast
import json
import math
import pytest
import test_g31_circulation_original_route_update as fixtures
from scripts.experiments.g31_ics_circulation import probe_original_route_update_eligibility as p
from scripts.experiments.g31_ics_circulation import verify_original_route_update_eligibility as v


def start():
    session = fixtures.Fixture(); calls = [0]
    original = session.observe_protocol
    update = p.RouteUpdate(session, fixtures.OWNER)
    def observed(owner):
        assert update.started_ns is not None and p.ROOT_ID in update.bridge.lineage.roots
        calls[0] += 1
        return original(owner)
    session.observe_protocol = observed; update.start()
    return session, update, calls


def submitted():
    session, update, calls = start(); session.physical_time = 9603.5; update.step()
    assert len(session.submits) == 1
    return session, update, calls


def test_only_first_root_fresh_view_derives_earliest_wakeup():
    session, update, calls = start()
    assert calls == [1] and session.submits == []
    assert update.started_ns < update.bridge.lineage.roots[p.ROOT_ID]["observation"]["wall_ns"]
    assert update.next_probe == p.initial_warm_target(update) == 9603.5
    assert update.eligibility_schedule == {"first_observed_at": 9600., "source_service_seconds": 1.5,
        "wire_seconds": 2., "deadline": 9603.5, "fired_at": None,
        "source": "initial_admitted_root_fresh_view", "initial_candidate_count": 1}


def test_second_fresh_view_keeps_exact_wire_and_retry_period():
    session, update, calls = submitted()
    assert calls == [2] and update.eligibility_schedule["fired_at"] == 9603.5
    assert session.submits[0]["message_delay"] == 2. and session.submits[0]["expiry"] == 9723.5
    assert update.next_probe == 9663.5
    assert update.client.state["retry_period"] == 60.
    session.physical_time = 9663.5; update.step()
    assert len(session.submits) == 2 and session.submits[0] == session.submits[1]
    assert update.intent.decision["first_observation"]["at"] == 9600.


@pytest.mark.parametrize("service", [0., 1.5, .1, 1./3])
def test_floating_deadline_never_precedes_existing_guard(service):
    due = p.eligibility_deadline(9600., service)
    assert due > 9600. and due-9600. >= 2.+service
    assert due == 9600.+2.+service or due == math.nextafter(9600.+(2.+service), math.inf)


@pytest.mark.parametrize("at,service", [(True, 1.5), (9600., False), (float('inf'), 1.5), (9600., float('nan')), (9600., -1.)])
def test_invalid_public_deadline_data_rejected(at, service):
    with pytest.raises(ValueError): p.eligibility_deadline(at, service)


def test_early_second_step_rejected_before_native_read_or_submit():
    session, update, calls = start(); session.physical_time = 9603.499
    with pytest.raises(ValueError, match="early_second_observation"): update.step()
    assert calls == [1] and not session.submits


@pytest.mark.parametrize("mutation", ["generation", "full_receiver", "left_source"])
def test_time_alone_never_authorizes_a_changed_or_blocked_candidate(mutation):
    session, update, calls = start(); original = session.observe_protocol
    def changed(owner):
        view = original(owner)
        if mutation == "generation": view["trays"][0]["generation"] += 1
        elif mutation == "full_receiver": view["node_contracts"][1]["occupancy"] = 4
        else: view["trays"][0]["node"] = 113
        return view
    session.observe_protocol = changed; session.physical_time = 9603.5; update.step()
    assert not session.submits and not update.closed and calls == [2]
    assert update.next_probe == 9663.5 and update.eligibility_schedule["fired_at"] == 9603.5


def test_absent_initial_candidate_preserves_old_polling_without_added_horizon():
    session = fixtures.Fixture(); session.observe_protocol = lambda owner: {**fixtures.view(session.physical_time), "trays": []}
    update = p.RouteUpdate(session, fixtures.OWNER); update.start()
    assert update.eligibility_schedule is None and update.next_probe == 9660.
    assert p.initial_warm_target(update) == 9900.


@pytest.mark.parametrize("ack,entry,exitproof", [(True, False, False), (True, True, False), (False, True, True)])
def test_ack_or_reservation_or_edge_alone_still_cannot_close(ack, entry, exitproof):
    session, update, _ = submitted(); session.physical_time = 9605.7
    if ack: session.ack = {"sequence": 1, "status": "updated", "executed_at": 9605.5,
        "completed_at": 9605.5, "delivered_at": 9605.7, "result_id": session.submits[0]["request_id"]}
    if entry:
        session.edge = {"edge_from": 112, "edge_to": 113, "traversal_id": 10}
        if exitproof: session.edge["edge_exit_at"] = 9607.
    update.step(); assert not update.closed


def test_exact_actual_ack_edge_and_drain_close_same_root():
    session, update, _ = submitted(); session.physical_time = 9605.7
    session.ack = {"sequence": 1, "status": "updated", "executed_at": 9605.5,
        "completed_at": 9605.5, "delivered_at": 9605.7, "result_id": session.submits[0]["request_id"]}
    session.edge = {"edge_from": 112, "edge_to": 113, "traversal_id": 10, "edge_exit_at": 9607.}
    session.drain_complete = False; update.step(); assert not update.closed
    session.drain_complete = True; update.step(); assert update.closed
    assert json.loads(json.loads(update.returned)["output"])["disposition"] == "completed"
    assert len(update.bridge.lineage.roots) == 1


def test_native_boundary_forwarder_preserves_actual_response_and_deadline(monkeypatch):
    session, update, _ = start(); calls = []
    response = {"status": "horizon_reached", "timestamp_complete": True, "notifications": {}, "physical_time": 9603.5}
    def advance(owners, after, horizon, *, max_events):
        calls.append((horizon, max_events)); session.physical_time = horizon; return response
    session.advance_until_owner_notification = advance
    monkeypatch.setattr(p.base, "invoke_root", lambda *args: None)
    actual = p.Boundary(session, update, []).advance_until_owner_notification([fixtures.OWNER], {}, 9603.5, max_events=100000)
    assert actual is response and calls == [(9603.5, 100000)]


def target_fixture(target=9603.5, status="reached"):
    item = {"target": target, "status": status, "physical_time": target}
    part = {"status": status, "control_continuation": {"requested_horizon": target},
        "controller_state": {"native_timestamp_complete": status == "reached"},
        "native_batches": [{"start_at": 9600., "end_at": target, "requested_public_deadline": target}]}
    return item, part


def test_real_horizons_keep_budget_cut_then_due_then_final():
    _, update, _ = start(); root = update.snapshot(); state = {"done": False}
    v.validate_warm_target(*target_fixture(status="control_budget_exhausted"), root, state)
    assert not state["done"]
    v.validate_warm_target(*target_fixture(), root, state); assert state["done"]
    v.validate_warm_target(*target_fixture(target=9900.), root, state)


@pytest.mark.parametrize("mutation", ["skipped_due", "fake_target", "partial_timestamp", "native_overrun", "unexpected_status"])
def test_missing_or_false_native_due_boundary_rejected(mutation):
    _, update, _ = start(); item, part = target_fixture()
    if mutation == "skipped_due": item, part = target_fixture(target=9900.)
    elif mutation == "fake_target": part["control_continuation"]["requested_horizon"] = 9900.
    elif mutation == "partial_timestamp": part["controller_state"]["native_timestamp_complete"] = False
    elif mutation == "native_overrun": part["native_batches"][0]["end_at"] += 1.
    else: part["status"] = "other"
    with pytest.raises(ValueError): v.validate_warm_target(item, part, update.snapshot(), {"done": False})


def prefix_fixture():
    return {"wall_seconds": 1., "control_records": [{"compute_wall_ms": 1., "compute_cpu_ms": 0., "at": 9600.}],
        "native_batches": [{"wall_ms": 1., "cpu_ms": 0., "requested_public_deadline": 9600.}],
        "client_calls": [{"submit_compute_ms": 1., "at": 9600.}],
        "result": {"advance": {"wall_seconds": 1., "physical_time": 9600.}},
        "controller_state": {"start": 0., "next_tick": 161, "pending_owners": ["A"]}}


def test_only_exact_diagnostic_fields_removed_without_mutating_raw():
    part = prefix_fixture(); original = deepcopy(part); stripped = v.prefix_semantics(part)
    assert part == original and stripped["controller_state"] == original["controller_state"]
    assert stripped["control_records"][0] == {"at": 9600.}
    changed = deepcopy(part); changed["controller_state"]["next_tick"] += 1
    assert v.prefix_semantics(changed) != stripped
    changed = deepcopy(part); changed["result"]["advance"]["physical_time"] += 1
    assert v.prefix_semantics(changed) != stripped


@pytest.mark.parametrize("value", [True, -1., float('nan'), float('inf')])
def test_invalid_diagnostic_clock_cannot_be_erased(value):
    part = prefix_fixture(); part["wall_seconds"] = value
    with pytest.raises(ValueError): v.prefix_semantics(part)


def test_frozen_base_identity_and_new_source_closure():
    assert p.old.sha(p.base.__file__) == p.BASE_SHA
    names = {x.name for x in p.source_paths()}
    assert {"probe_original_route_update.py", "probe_original_route_update_eligibility.py",
        "verify_original_route_update_eligibility.py", __file__.split('\\')[-1].split('/')[-1]} <= names
    assert p.CASES == {"baseline": 0, "drop_first_ack": 1, "ack_withheld_in_window": 100}
    assert p.PARENT_SECONDS == 600. and p.HORIZON == 9900. and p.ADMISSION == 9600.


def test_background_controller_call_and_state_retention_ast_unchanged():
    def control_ast(path):
        tree = ast.parse(p.Path(path).read_text(encoding="utf8"))
        worker = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "worker")
        control = next(n for n in worker.body if isinstance(n, ast.FunctionDef) and n.name == "control")
        return ast.dump(control, include_attributes=False)
    assert control_ast(p.__file__) == control_ast(p.base.__file__)
    assert p.Boundary is p.base.Boundary and p.invoke_root is p.base.invoke_root
