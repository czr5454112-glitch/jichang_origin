"""Opt-in export deferral against a same-timestamp, budgeted fake scheduler.

No native session is constructed. The real controller/client still own every
submit, retry, delivered-ACK refresh and continuation transition.
"""
from copy import deepcopy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_protocol_v2 as controller


class Session:
    def __init__(self):
        self.physical_time = 0.
        self.pending = []
        self.requests = {}
        self.events = []
        self.exports = []
        self.responses = []

    def advance_to(self, target, max_events=1000000):
        processed = 0
        while self.pending and self.pending[0][0] <= target and processed < max_events:
            at, identity, phase = self.pending.pop(0)
            self.physical_time = at
            self.events.append((at, identity, phase))
            if phase == "accept":
                self.pending.insert(0, (at, identity, "received"))
            else:
                self.requests[identity]["received"] = True
            processed += 1
        complete = not self.pending or self.pending[0][0] > target
        if complete:
            self.physical_time = target
        response = {"physical_time": self.physical_time,
                    "status": "reached" if complete else "budget_exhausted",
                    "horizon_complete": complete, "processed_events": processed}
        self.responses.append(response)
        return response

    def protocol_demand_signature(self, owner):
        return owner + ":unchanged"

    def observe_protocol_control(self, owner):
        available = not any(row["at"] == self.physical_time for row in self.requests.values())
        return {"now": self.physical_time, "owner_id": owner,
                "client_transfer_ledger": [], "available": available}

    def submit_protocol_transfer(self, request):
        identity = request["request_id"]
        if identity not in self.requests:
            self.requests[identity] = {"at": self.physical_time,
                                       "payload": deepcopy(request), "received": False}
            self.pending.append((self.physical_time, identity, "accept"))
        return {"status": "pending"}

    def protocol_request(self, owner, identity):
        row = self.requests[identity]
        return {"last_delivered_ack": {"status": "received" if row["received"] else "pending",
                                       "received_at": row["at"] if row["received"] else -1.}}

    def result_at(self, target):
        self.exports.append(target)
        progress = self.advance_to(target)
        return {"physical_clock": self.physical_time, "advance": progress,
                "requests": deepcopy(self.requests), "events": deepcopy(self.events)}


def planner(observation, **options):
    return {"intents": [{"tray_id": "E", "source": 0, "destination": 1}]
            if observation["available"] else []}


@pytest.fixture(autouse=True)
def no_services(monkeypatch):
    monkeypatch.setattr(controller, "_publish_services", lambda *a, **kw: [])


def run(session, horizon, **options):
    return controller.run_airport_bounded_protocol_control(
        session, ["A"], horizon=horizon, control_period=1., command_delay=0.,
        planner=planner, planner_identity="same_timestamp_fake", **options)


def canonical(value):
    measurements = {"wall_seconds", "wall_ms", "cpu_ms", "compute_ms",
                    "submit_compute_ms", "preparation_compute_ms"}
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k not in measurements}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def test_default_and_explicit_false_preserve_outputs_without_new_metadata():
    a, b = Session(), Session()
    default = run(a, 3.)
    explicit = run(b, 3., defer_intermediate_result=False)
    assert canonical(default) == canonical(explicit)
    assert a.exports == b.exports == [3.]
    assert "boundary_advance" not in default and "result_export" not in default
    assert "defer_intermediate_result" not in default["controller_state"]["config"]


@pytest.mark.parametrize("owned", [False, True])
def test_segmented_deferral_retains_protocol_physical_state_and_final_evidence(owned):
    def execute(defer):
        session = Session()
        first = run(session, 2.5, defer_intermediate_result=defer, _consume_state=owned)
        # The public JSON continuation retains immutable client payloads and ACKs.
        state = json.loads(json.dumps(first["controller_state"]))
        second = run(session, 6., state=state, _consume_state=owned)
        return session, first, second
    old_session, old_first, old_last = execute(False)
    new_session, new_first, new_last = execute(True)
    assert old_session.exports == [2.5, 6.]
    assert new_session.exports == [6.]
    assert new_first["result"] is None and new_first["status"] == "reached"
    assert new_first["control_continuation"]["timestamp_complete"] is True
    assert new_first["controller_state"]["control_boundary_complete"] is True
    assert new_first["result_export"] == "deferred_complete_boundary"
    assert new_first["boundary_advance"]["physical_time"] == 2.5
    assert new_first["boundary_advance"]["horizon_complete"] is True
    assert new_first["controller_state"] == old_first["controller_state"]
    assert canonical(new_last) == canonical(old_last)
    assert new_session.requests == old_session.requests
    assert new_session.events == old_session.events
    for key in ("client_calls", "control_records", "native_batches"):
        assert canonical(new_first[key]) == canonical(old_first[key])


def test_final_drain_closes_work_submitted_after_the_earlier_timestamp_receipt():
    session = Session()
    result = run(session, 0., defer_intermediate_result=True, event_budget=2)
    assert session.exports == []
    assert result["status"] == "reached"
    assert session.pending == [] and len(session.events) == 2
    assert result["boundary_advance"] == session.responses[-1]
    assert result["boundary_advance"]["processed_events"] == 2
    assert result["native_batches"][-1]["processed_events"] == 2
    assert all(row["received"] for row in session.requests.values())


@pytest.mark.parametrize("defer", [False, True])
def test_numeric_clock_without_same_timestamp_completion_never_exports_or_resumes(defer):
    session = Session()
    result = run(session, 0., defer_intermediate_result=defer, event_budget=1)
    assert session.physical_time == 0. and session.pending  # remaining microphase at the same clock
    assert result["status"] == "budget_exhausted" and result["result"] is None
    assert result["controller_state"]["control_boundary_complete"] is False
    assert result["control_continuation"]["timestamp_complete"] is False
    assert session.exports == []
    if defer:
        assert result["boundary_advance"]["horizon_complete"] is False
        assert result["result_export"] == "not_exported_incomplete"
    with pytest.raises(ValueError, match="partial_tick_resume"):
        run(session, 1., state=result["controller_state"])


def test_soft_deadline_exports_only_completed_actual_timestamp_even_when_deferred():
    session = Session()
    first = run(session, 1., defer_intermediate_result=True)
    stopped = run(session, 10., state=first["controller_state"],
                  defer_intermediate_result=True, soft_deadline=1., soft_clock=lambda: 2.)
    assert stopped["status"] == "soft_deadline_reached"
    assert session.exports == [2.] and session.physical_time == 2.
    assert stopped["result"]["physical_clock"] == 2.
    assert stopped["result_export"] == "exported_soft_stop"
    assert stopped["boundary_advance"]["physical_time"] == 2.
    assert stopped["control_continuation"]["next_control_tick_pending"] is True
    assert stopped["controller_state"]["next_tick"] == 2


def test_boundary_receipt_is_a_copy_not_a_live_native_response_alias():
    session = Session()
    result = run(session, 0., defer_intermediate_result=True)
    expected = deepcopy(result["boundary_advance"])
    session.responses[-1].update(status="mutated", horizon_complete=False)
    assert result["boundary_advance"] == expected


@pytest.mark.parametrize("flag", [0, 1, None, "true", [], {}])
def test_invalid_flag_rejected_before_native_or_controller_mutation(flag):
    session = Session()
    with pytest.raises(ValueError, match="invalid_defer_intermediate_result"):
        run(session, 1., defer_intermediate_result=flag)
    assert session.physical_time == 0. and session.responses == []
    assert session.requests == {} and session.exports == []


def test_soft_export_exception_still_poisons_owned_state():
    session = Session()
    first = run(session, 1., defer_intermediate_result=True, _consume_state=True)
    state = first["controller_state"]
    def fail(target):
        raise RuntimeError("export failure")
    session.result_at = fail
    with pytest.raises(RuntimeError, match="export failure"):
        run(session, 3., state=state, _consume_state=True, defer_intermediate_result=True,
            soft_deadline=1., soft_clock=lambda: 2.)
    assert state["control_boundary_complete"] is False

