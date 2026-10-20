"""Private ownership transfer parity using the real client and fake endpoints."""
from copy import deepcopy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_protocol_v2 as controller


class Session:
    def __init__(self):
        self.physical_time = 0.
        self.requests = {}
        self.transferred = False
        self.fail = False
        self.budget_fail = False

    def advance_to(self, at, max_events):
        self.physical_time = at
        return {"status": "budget_exhausted" if self.budget_fail else "reached",
                "horizon_complete": not self.budget_fail, "processed_events": 1}

    def protocol_demand_signature(self, owner):
        return owner + ":unchanged"

    def submit_protocol_command(self, payload):
        self.requests.setdefault(payload["request_id"], (self.physical_time, deepcopy(payload)))
        if self.fail:
            raise RuntimeError("fake interrupted submit")
        return {"status": "pending"}

    def submit_protocol_transfer(self, payload):
        self.transferred = True
        return self.submit_protocol_command(payload)

    def protocol_command(self, owner, identity):
        at, payload = self.requests[identity]
        if self.physical_time < at + 2.:
            return {"last_delivered_ack": {"status": "pending"}}
        ack = {"status": "delivered" if "kind" in payload else "received",
               "delivered_at": at + 2.,
               "captured_demand_signature": owner + ":unchanged"}
        if payload.get("kind") == "planning_snapshot":
            ack["planning_snapshot"] = {"capture": {
                "source_owner": owner, "target_owner": payload["target_owner"],
                "captured_at": at, "valid_until": payload["expiry"],
                "jobs": [{"id": "retained", "nested": list(range(64))}]}}
        return {"last_delivered_ack": ack}

    protocol_request = protocol_command

    def protocol_planning_snapshots(self, owner):
        return []

    def observe_protocol_control(self, owner):
        return {"now": self.physical_time, "owner_id": owner, "client_transfer_ledger": [],
                "available": owner == "A" and not self.transferred}

    def result_at(self, horizon):
        assert horizon == self.physical_time
        return {"physical_clock": horizon, "requests": deepcopy(self.requests),
                "advance": {"status": "reached", "horizon_complete": True}}


def planner(obs, **options):
    return {"intents": [{"tray_id": "E", "source": 0, "destination": 1}]
            if obs["available"] else []}


OPTIONS = dict(control_period=1., planner=planner, planner_identity="owned_fake",
               inventory_snapshots=True, inventory_snapshot_validity=8.,
               inventory_snapshot_refresh_period=3.)


@pytest.fixture(autouse=True)
def services(monkeypatch):
    monkeypatch.setattr(controller, "_publish_services", lambda *a, **kw: [])


def canonical(value, *, segmented=False):
    """Only named measurement fields and segment-local trace counters removed."""
    omit = {"wall_seconds", "wall_ms", "cpu_ms", "submit_compute_ms", "compute_ms",
            "preparation_compute_ms", "offline_evaluator_ms",
            "offline_tick_start_observer_ms", "offline_tick_start_observer_seconds",
            "endpoint_read_ms", "byte_measurement_ms"}
    if segmented:
        omit.add("trace_sequence")
    if isinstance(value, dict):
        return {k: canonical(v, segmented=segmented) for k, v in value.items() if k not in omit}
    if isinstance(value, (list, tuple)):
        return [canonical(v, segmented=segmented) for v in value]
    return value


def run(session, horizon, **changes):
    return controller.run_airport_bounded_protocol_control(
        session, ["A", "B"], horizon=horizon, **OPTIONS, **changes)


@pytest.mark.parametrize("split", [False, True])
def test_owned_full_outputs_ack_history_and_observer_parity(split):
    def execute(consume):
        session, ticks, precommit = Session(), [], []
        def capture(destination, **kw):
            current = deepcopy(kw["controller_state"])
            current["client"] = deepcopy(kw["client_state"])
            destination.append(current)
        opts = dict(_consume_state=consume,
                    tick_start_observer=lambda **kw: capture(ticks, **kw),
                    precommit_observer=lambda **kw: capture(precommit, **kw))
        if split:
            first = run(session, 2.5, **opts)
            second = run(session, 6., state=first["controller_state"], **opts)
            outputs = [first, second]
        else:
            outputs = [run(session, 6., **opts)]
        return canonical(outputs), ticks, precommit
    copied, copied_ticks, copied_precommit = execute(False)
    owned, owned_ticks, owned_precommit = execute(True)
    # The first result in owned mode has been relinquished to its successor.
    if split:
        copied[0].pop("controller_state")
        owned[0].pop("controller_state")
    assert owned == copied
    assert owned_ticks == copied_ticks
    assert owned_precommit == copied_precommit
    history = owned[-1]["controller_state"]["client"]["outbox"]
    captures = [r["client_view"]["last_delivered_ack"].get("planning_snapshot")
                for r in history.values() if r.get("terminal")]
    assert sum(c is not None for c in captures) >= 4
    assert all(c["capture"]["jobs"][0]["nested"] == list(range(64)) for c in captures if c)
    assert any(call["retry"] for call in owned[-1]["client_calls"]) or split


@pytest.mark.parametrize("consume", [False, True])
def test_continuous_and_segmented_control_have_exact_semantic_state_and_calls(consume):
    whole = run(Session(), 6., _consume_state=consume)
    session = Session()
    first = run(session, 2.5, _consume_state=consume)
    second = run(session, 6., state=first["controller_state"], _consume_state=consume)
    assert whole["controller_state"] == second["controller_state"]
    assert whole["result"] == second["result"]
    for key in ("client_calls", "control_records", "inventory_snapshot_reads"):
        assert canonical(whole[key], segmented=True) == canonical(
            first[key] + second[key], segmented=True)


def test_default_preserves_input_and_owned_transfers_both_controller_and_client_identity():
    for consume in (False, True):
        session = Session()
        first = run(session, 2.)
        state = first["controller_state"]
        previous = deepcopy(state)
        nested = state["client"]
        result = run(session, 6., state=state, _consume_state=consume)
        assert (result["controller_state"] is state) is consume
        assert (result["controller_state"]["client"] is nested) is consume
        if consume:
            assert state["next_tick"] == 7 and state != previous
        else:
            assert state == previous
        assert "_consume_state" not in result["controller_state"]["config"]


@pytest.mark.parametrize("consume", [False, True])
@pytest.mark.parametrize("location", ["observer", "submit", "result"])
def test_interruption_does_not_offer_consumed_partial_state_for_reuse(consume, location):
    session = Session()
    first = run(session, 2.)
    state = first["controller_state"]
    previous = deepcopy(state)
    extra = {}
    def fail(**kw):
        raise RuntimeError("fake interrupted observer")
    if location == "observer":
        extra["precommit_observer"] = fail
    elif location == "submit":
        session.fail = True  # inventory renewal at tick 3
    else:
        session.result_at = lambda horizon: fail()
    with pytest.raises(RuntimeError, match="fake interrupted"):
        run(session, 4., state=state, _consume_state=consume, **extra)
    if consume:
        assert state["control_boundary_complete"] is False
        for option in (False, True):
            with pytest.raises(ValueError, match="partial_tick_resume"):
                run(session, 5., state=state, _consume_state=option)
    else:
        assert state == previous


@pytest.mark.parametrize("consume", [False, True])
def test_native_partial_and_soft_stop_flags_are_unchanged(consume):
    session = Session()
    first = run(session, 2.)
    state = first["controller_state"]
    session.budget_fail = True
    partial = run(session, 4., state=state, _consume_state=consume)
    assert partial["status"] == "budget_exhausted"
    assert partial["controller_state"]["control_boundary_complete"] is False
    session = Session()
    first = run(session, 2.)
    state = first["controller_state"]
    stopped = run(session, 4., state=state, _consume_state=consume,
                  soft_deadline=1., soft_clock=lambda: 2.)
    assert stopped["status"] == "soft_deadline_reached"
    assert stopped["controller_state"]["control_boundary_complete"] is True
    assert stopped["controller_state"]["next_tick"] == 3


def test_invalid_consume_flag_is_rejected_before_session_mutation():
    session = Session()
    with pytest.raises(ValueError, match="invalid_consume_state"):
        run(session, 2., _consume_state=1)
    assert session.physical_time == 0. and session.requests == {}


def test_native_tuple_observation_compares_only_after_json_container_normalization():
    native = {"node_records": [(0, 1, .001, 0, 0, [1])],
              "edge_records": [(0, 1, 1., 1.)], "trays": [{"node": 0}]}
    saved = json.loads(json.dumps(native))
    assert native != saved  # Direct equality cannot certify native JSON replay.
    assert canonical(native) == canonical(saved)
    changed = deepcopy(saved)
    changed["trays"][0]["node"] = 1
    assert canonical(native) != canonical(changed)


def test_owned_mode_avoids_all_three_full_history_copies(monkeypatch):
    original = deepcopy
    for consume, expected in ((False, 3), (True, 0)):
        session = Session()
        state = run(session, 2.)["controller_state"]
        copies = []
        def trace(value, memo=None, _nil=[]):
            if memo is None and isinstance(value, dict) and value.get("schema") in {
                    "g31.protocol_controller_state.v3", "g31.protocol_client_state.v1"}:
                copies.append(value["schema"])
            return original(value, memo)
        with monkeypatch.context() as patch:
            patch.setattr(controller.copy, "deepcopy", trace)
            run(session, 4., state=state, _consume_state=consume)
        assert len(copies) == expected
