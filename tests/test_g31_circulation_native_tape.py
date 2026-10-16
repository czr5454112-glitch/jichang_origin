import copy

import pytest

from scripts.experiments.g31_ics_circulation.reconstruct_native_tape import (
    NativeTapeReconstructor, TapeMismatch, validate_call_assignment)


SEAL = "a" * 64


def notice(sequence):
    return {"sequence": sequence, "observed_at": 1., "change_mask": 16}


def owner(sequence, name, at, *, notifications=None, refreshed=None, publications=None, attempts=None):
    return {"trace_sequence": sequence, "owner_id": name, "at": at,
            "causes": {"notification": notifications} if notifications is not None else {},
            "refreshed": refreshed or [], "publications": publications or [],
            "service_actions": [], "attempts": attempts or []}


def boundary(sequence, start, end, status, complete=True):
    return {"trace_sequence": sequence, "start_at": start, "end_at": end,
            "requested_public_deadline": end, "status": status, "timestamp_complete": complete}


def fixture():
    a = {"request_id": "A:d0", "owner_id": "A", "kind": "demand", "target_owner": "B"}
    b = {"request_id": "B:t0", "owner_id": "B", "tray_id": "T"}
    pending = {"status": "pending", "reason": "enqueued"}
    retried = {"status": "pending", "reason": "retry_enqueued"}
    query_pending = {"request_id": "A:d0", "last_delivered_ack": {"status": "pending"}}
    query_final = {"request_id": "A:d0", "last_delivered_ack": {"status": "delivered"}}
    calls = [{"at": 0., "retry": False, "kind": "demand", "request": a, "reply": pending},
             {"at": 1., "retry": True, "kind": "demand", "request": a, "reply": retried},
             {"at": 1., "retry": False, "kind": "transfer", "request": b, "reply": pending}]
    records = [owner(1, "A", 0., publications=[{"request_id": "A:d0", "reply": pending}]),
               owner(2, "B", 0.),
               owner(4, "A", 1., notifications=notice(1),
                     refreshed=[{"request_id": "A:d0", "kind": "demand", "view": query_pending}]),
               owner(5, "B", 1., notifications=notice(1), attempts=[{"request_id": "B:t0", "reply": pending}]),
               owner(7, "A", 1., notifications=notice(2),
                     refreshed=[{"request_id": "A:d0", "kind": "demand", "view": query_final}])]
    state = {"config": {"owners": ["A", "B"], "retry_period": 1.},
             "after_sequences": {"A": 2, "B": 1}, "pending_causes": {},
             "native_timestamp_complete": False,
             "client": {"outbox": {
                 "A:d0": {"payload": a, "kind": "demand", "created_at": 0., "next_retry": 2.,
                          "submission_reply": retried, "client_view": query_final},
                 "B:t0": {"payload": b, "kind": "transfer", "created_at": 1., "next_retry": 2.,
                          "submission_reply": pending}}}}
    part = {"control_records": records, "client_calls": calls, "native_batches": [
        boundary(0, 0., 0., "horizon_reached"), boundary(3, 0., 1., "notified"),
        boundary(6, 1., 1., "notified")], "controller_state": state, "result": None,
        "status": "control_budget_exhausted",
        "control_continuation": {"physical_time": 1., "requested_horizon": 2.,
                                 "status": "control_budget_exhausted"}}
    responses = [(0., {}, {"A": 0, "B": 0}, "horizon_reached", True),
                 (1., {"A": notice(1), "B": notice(1)}, {"A": 0, "B": 0}, "notified", True),
                 (1., {"A": notice(2)}, {"A": 1, "B": 1}, "notified", True)]
    return part, Session(responses, calls, [query_pending, query_final])


class Session:
    def __init__(self, responses, calls, views):
        self.physical_time = 0.
        self.responses, self.calls, self.views = copy.deepcopy((responses, calls, views))
        self.log = []

    def advance_until_owner_notification(self, owners, after, deadline, *, max_events):
        at, notices, expected_after, status, complete = self.responses.pop(0)
        assert owners == ["A", "B"] and after == expected_after and max_events == 9
        assert at <= deadline
        self.physical_time = at
        self.log.append(("advance", deadline, after))
        return {"physical_time": at, "notifications": notices, "status": status,
                "timestamp_complete": complete}

    def _send(self, payload, kind):
        expected = self.calls.pop(0)
        assert payload == expected["request"] and self.physical_time == expected["at"]
        assert (kind == "transfer") == (expected["kind"] == "transfer")
        self.log.append((kind, copy.deepcopy(payload)))
        return expected["reply"]

    def submit_protocol_transfer(self, payload):
        return self._send(payload, "transfer")

    def submit_protocol_command(self, payload):
        return self._send(payload, "command")

    def protocol_command(self, owner, identity):
        self.log.append(("query", owner, identity))
        return self.views.pop(0)

    protocol_request = protocol_command

    def checkpoint(self):
        return ("opaque_native_checkpoint", self.physical_time)

    def offline_state_sha256(self):
        return SEAL


def test_replay_orders_retries_and_multiple_owners_at_same_timestamp_and_seal_gates():
    part, session = fixture()
    original = copy.deepcopy(part)
    replay = NativeTapeReconstructor(session, event_budget=9)
    report = replay.replay_part(part, retain_checkpoint="cut")
    assert report["submissions"] == 3 and report["owners"] == 5 and report["queries"] == 2
    assert report["native_boundaries"] == 3
    with pytest.raises(TapeMismatch, match="unverified_session"):
        replay.verified_session()
    with pytest.raises(TapeMismatch, match="unverified_checkpoint"):
        replay.verified_checkpoint("cut")
    assert replay.finish(SEAL)["status"] == "verified_against_known_native_seal"
    assert replay.verified_session() is session
    assert replay.verified_checkpoint("cut") == ("opaque_native_checkpoint", 1.)
    assert part == original and not session.calls and not session.views and not session.responses
    assert not report["native_json_restore"] and not report["policy_reexecuted"]


@pytest.mark.parametrize("defect", ["gap", "duplicate", "call_owner", "call_time", "mutated_retry",
    "reply", "cause", "cursor", "unknown_service", "unused_call", "next_retry", "view", "boundary"])
def test_tampered_tape_fails_closed(defect):
    part, session = fixture()
    if defect == "gap": part["native_batches"][0]["trace_sequence"] = 10
    elif defect == "duplicate": part["control_records"][0]["trace_sequence"] = 0
    elif defect == "call_owner": part["client_calls"][0]["request"] = dict(part["client_calls"][0]["request"], owner_id="B")
    elif defect == "call_time": part["client_calls"][0]["at"] = .01
    elif defect == "mutated_retry": part["client_calls"][1]["request"] = dict(part["client_calls"][1]["request"], target_owner="A")
    elif defect == "reply": part["client_calls"][1]["reply"] = {"status": "rejected"}
    elif defect == "cause": part["control_records"][2]["causes"]["notification"]["sequence"] = 3
    elif defect == "cursor": part["controller_state"]["after_sequences"]["A"] = 3
    elif defect == "unknown_service": part["control_records"][0]["service_actions"] = [{"kind": "invented"}]
    elif defect == "unused_call": part["client_calls"].append(copy.deepcopy(part["client_calls"][-1]))
    elif defect == "next_retry": part["controller_state"]["client"]["outbox"]["A:d0"]["next_retry"] = 3.
    elif defect == "view": part["control_records"][2]["refreshed"][0]["view"] = {"status": "invented"}
    elif defect == "boundary": part["native_batches"][1]["end_at"] = .9
    replay = NativeTapeReconstructor(session, event_budget=9)
    with pytest.raises(TapeMismatch): replay.replay_part(part)
    assert replay.failed
    with pytest.raises(TapeMismatch): replay.finish(SEAL)
    with pytest.raises(TapeMismatch): replay.verified_session()


@pytest.mark.parametrize("seal", [None, "", "b" * 64, "A" * 64])
def test_missing_or_wrong_known_seal_never_releases_session(seal):
    part, session = fixture()
    replay = NativeTapeReconstructor(session, event_budget=9)
    replay.replay_part(part)
    with pytest.raises(TapeMismatch): replay.finish(seal)
    assert replay.failed


def test_partial_native_budget_cut_remains_replayable_without_result_or_notifications():
    part, session = fixture()
    replay = NativeTapeReconstructor(session, event_budget=9)
    replay.replay_part(part)
    partial = copy.deepcopy(part)
    partial.update(control_records=[], client_calls=[], result=None, status="native_budget_exhausted",
                   native_batches=[boundary(8, 1., 1.2, "budget_exhausted", False)])
    partial["control_continuation"].update(physical_time=1.2, status="native_budget_exhausted")
    session.responses.append((1.2, {}, {"A": 2, "B": 1}, "budget_exhausted", False))
    replay.replay_part(partial)
    assert replay.finish(SEAL)["physical_time"] == 1.2


def test_pending_notice_is_preserved_across_shards_until_its_owner_acts():
    part, session = fixture()
    replay = NativeTapeReconstructor(session, event_budget=9)
    replay.replay_part(part)
    shard = copy.deepcopy(part)
    shard.update(control_records=[], client_calls=[], native_batches=[boundary(8, 1., 1., "notified")])
    shard["controller_state"]["after_sequences"]["B"] = 2
    shard["controller_state"]["pending_causes"] = {"B": {"notification": notice(2)}}
    session.responses.append((1., {"B": notice(2)}, {"A": 2, "B": 1}, "notified", True))
    replay.replay_part(shard)
    next_shard = copy.deepcopy(shard)
    next_shard.update(native_batches=[], control_records=[owner(9, "B", 1., notifications=notice(2))])
    next_shard["controller_state"]["pending_causes"] = {}
    replay.replay_part(next_shard)
    assert replay.finish(SEAL)["parts"] == 3


def test_immediate_rejection_has_no_implicit_retry():
    part, session = fixture()
    # No native state transition is inferred from a rejected call. The source
    # owner record and immutable native reply are still both required.
    part["control_records"] = part["control_records"][:2]
    part["native_batches"] = part["native_batches"][:1]
    part["client_calls"] = part["client_calls"][:1]
    rejection = {"status": "rejected", "reason": "owner"}
    part["client_calls"][0]["reply"] = rejection
    part["control_records"][0]["publications"][0]["reply"] = rejection
    outbox = part["controller_state"]["client"]["outbox"]
    del outbox["B:t0"]
    outbox["A:d0"].update(next_retry=1., submission_reply=rejection)
    del outbox["A:d0"]["client_view"]
    part["controller_state"]["after_sequences"] = {"A": 0, "B": 0}
    part["control_continuation"]["physical_time"] = 0.
    session.calls = copy.deepcopy(part["client_calls"])
    replay = NativeTapeReconstructor(session, event_budget=9)
    replay.replay_part(part)
    assert replay.finish(SEAL)["submissions"] == 1


def test_pure_mapping_labels_its_limited_evidence_and_preserves_same_time_order():
    part, _ = fixture()
    report = validate_call_assignment([part])
    assert report["owner_records"] == 5 and report["submissions"] == 3
    assert report["immutable_ids"] == 2 and report["retry_attempts"] == 1
    assert report["native_executed"] is False and report["native_state_equivalence_verified"] is False
    part["client_calls"][1], part["client_calls"][2] = part["client_calls"][2], part["client_calls"][1]
    with pytest.raises(TapeMismatch, match="submission_order_or_owner"):
        validate_call_assignment([part])


def test_pure_mapping_cannot_drop_a_retry_or_add_an_unattributed_call():
    part, _ = fixture()
    part["control_records"][2]["refreshed"] = []
    with pytest.raises(TapeMismatch):
        validate_call_assignment([part])
