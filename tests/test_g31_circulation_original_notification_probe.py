from copy import deepcopy
import pytest

from scripts.experiments.g31_ics_circulation.original_notification_probe import run_cohort
from scripts.experiments.g31_ics_circulation.replay_original_notification_probe import verify_raw


class Clock:
    def __init__(self): self.value = 0
    def __call__(self): self.value += 10; return self.value


class Session:
    """Explicit test double; no physical/native conformance claim."""
    def __init__(self, *, lost=False, budget=False):
        self.physical_time = 0.; self.sequence = 0; self.requests = {}; self.lost = lost; self.budget = budget

    def advance_until_owner_notification(self, owners, cursors, horizon, *, max_events):
        if self.budget: return {"status": "budget_exhausted", "timestamp_complete": False, "physical_time": 0., "notifications": {}}
        self.physical_time = min(horizon, self.physical_time+1.); self.sequence += 1
        return {"status": "notified", "timestamp_complete": True, "physical_time": self.physical_time,
                "notifications": {"A": {"sequence": self.sequence, "observed_at": self.physical_time, "change_mask": 1}}}

    def observe_protocol(self, owner):
        return {"schema": "g31.owner_protocol_observation.v1", "owner_id": owner, "now": self.physical_time,
            "jobs": [], "trays": [], "node_contracts": [{"node": 0, "resource_owner": owner}],
            "client_transfer_ledger": [], "delivered_messages": []}

    def advance_to(self, at, *, max_events):
        self.physical_time = at
        return {"status": "reached", "horizon_complete": True, "physical_time": at, "wall_seconds": 0.}

    def submit_protocol_command(self, payload):
        identity = payload["request_id"]
        old = self.requests.setdefault(identity, {"payload": deepcopy(payload), "attempts": 0})
        assert old["payload"] == payload
        old["attempts"] += 1
        return {"status": "pending", "request_id": identity}

    def protocol_command(self, owner, identity):
        ack = {} if self.lost else {"status": "delivered", "sequence": 1, "delivered_at": self.physical_time}
        return {"request_id": identity, "last_delivered_ack": ack}


def no_action(client, owner, owners, state, view): return {"selected": None}


def publication(client, owner, owners, state, view):
    identity, reply = client.submit(owner, "demand", {"target_owner": "B", "message_delay": 2., "publication_delay": .5})
    return {"request_id": identity, "reply": reply}


def test_actual_engine_noaction_path_retains12_native_boundaries_and_empty_scope():
    result = run_cohort(Session(), ["A"], clock=Clock(), proposal=no_action)
    assert result["status"] == "finite_cohort_closed"
    assert result["admitted_notification_boundaries"] == 12
    assert result["accounting_without_host_setup"]["bundle_denominator"] == 12
    assert result["accounting_without_host_setup"]["job_child_denominator"] == 0
    assert all(r["output"]["disposition"] == "no_action" for r in result["ledger"]["roots"].values())
    assert result["original_business_request_100ms_certified"] is False
    assert result["native_runtime_accepted"] is False


def test_actual_engine_submit_query_drain_output_and_tape_identity():
    result = run_cohort(Session(), ["A"], clock=Clock(), proposal=publication)
    assert result["status"] == "finite_cohort_closed", result["failures"]
    assert len(result["ledger"]["operations"]) == 12
    assert all(op["ack"]["body"]["status"] == "delivered" for op in result["ledger"]["operations"].values())
    tape = [r for c in result["chunks"] for r in c["service_tape"]]
    assert [r["ordinal"] for r in tape] == list(range(1, result["native_call_count"]+1))
    assert all(isinstance(r["args"], list) for r in tape)
    assert len([r for r in tape if r["endpoint"] == "submit_protocol_command"]) == 12


def test_actual_engine_missing_ack_tail_retains_all_roots_and_retries():
    result = run_cohort(Session(lost=True), ["A"], clock=Clock(), proposal=publication)
    assert result["status"] == "completion_tail_exhausted", result["failures"]
    assert result["admitted_notification_boundaries"] == 12
    assert len(result["ledger"]["roots"]) == 12
    assert all(op["ack"] is None and len(op["attempts"]) >= 2 for op in result["ledger"]["operations"].values())
    assert all(r["complete_compute_upper_ns"] is None for r in result["accounting_without_host_setup"]["roots"].values())
    assert any(b.get("not_admitted_owners") for b in result["ledger"]["batches"].values())


def test_partial_native_boundary_fails_closed_with_denominator():
    result = run_cohort(Session(budget=True), ["A"], clock=Clock(), proposal=no_action)
    assert result["status"] == "unknown_failed_or_budget_prefix"
    assert result["accounting_without_host_setup"]["pending_boundary_denominator"] == 1
    assert len(result["unflushed_service_tape"]) == 1


def test_stream_sink_retains_all_raw_ordinals_and_failures():
    chunks = []
    def sink(chunk):
        chunks.append(deepcopy(chunk))
        return {"index": chunk["index"], "ordinal_count": len(chunk["service_tape"])}
    result = run_cohort(Session(), ["A"], clock=Clock(), proposal=publication, chunk_sink=sink)
    assert result["status"] == "finite_cohort_closed"
    assert sum(len(c["service_tape"]) for c in chunks) == result["native_call_count"]
    assert all("service_tape" not in c for c in result["chunks"])


def test_failed_stream_write_keeps_unflushed_raw_and_does_not_claim_success():
    def sink(chunk): raise OSError("simulated_disk_error")
    result = run_cohort(Session(), ["A"], clock=Clock(), proposal=publication, chunk_sink=sink)
    assert result["status"] == "unknown_failed_or_budget_prefix"
    assert result["failures"] and result["unflushed_service_tape"]
    assert result["accounting_without_host_setup"]["bundle_denominator"] == 1


@pytest.mark.parametrize("policy,lost", [(no_action, False), (publication, False), (publication, True)])
def test_independent_replay_consumes_every_actual_endpoint_and_closure(policy, lost):
    raw = run_cohort(Session(lost=lost), ["A"], clock=Clock(), proposal=policy)
    result = verify_raw(raw, ["A"], raw["chunks"], mandatory_setup_start_ns=0, proposal=policy)
    assert result["root_count"] == 12
    assert result["closed_count"] == (0 if lost else 12)
    assert result["service_call_count"] == raw["native_call_count"]
    assert result["original_business_request_100ms_certified"] is False


@pytest.mark.parametrize("change", [
    lambda raw: raw["chunks"][0]["service_tape"].pop(),
    lambda raw: raw["chunks"][0]["service_tape"][0]["result"]["notifications"]["A"].update(sequence=999),
    lambda raw: raw["chunks"][0]["service_tape"][1]["result"].update(owner_id="B"),
    lambda raw: raw["chunks"][0]["service_tape"][-1]["args"][0].update(target_owner="foreign"),
    lambda raw: raw["ledger"]["roots"]["notification:0:A"]["output"].update(wall_ns=1),
    lambda raw: raw["ledger"]["roots"]["notification:0:A"]["observation"].update(call_ordinal=1),
    lambda raw: next(iter(raw["ledger"]["operations"].values()))["ack"].update(query_ordinal=1),
])
def test_tampered_notice_view_payload_missing_tape_or_lifecycle_fails_closed(change):
    raw = run_cohort(Session(), ["A"], clock=Clock(), proposal=publication)
    change(raw)
    with pytest.raises((ValueError, KeyError)):
        verify_raw(raw, ["A"], raw["chunks"], mandatory_setup_start_ns=0, proposal=publication)


def test_full_mandatory_setup_is_not_divided_across_many_requests():
    clock = Clock(); clock.value = 1000
    raw = run_cohort(Session(), ["A"], clock=clock, proposal=no_action)
    result = verify_raw(raw, ["A"], raw["chunks"], mandatory_setup_start_ns=0, proposal=no_action)
    assert result["mandatory_setup_ns"] > 1000
    assert all(r["complete_operation_upper_ns"] > 1000 for r in result["roots"].values())


@pytest.mark.parametrize("field,value", [("engine_start_ns", True), ("ended_ns", float("inf"))])
def test_noninteger_or_nonfinite_outer_lifetime_is_unknown(field, value):
    raw = run_cohort(Session(), ["A"], clock=Clock(), proposal=no_action)
    raw[field] = value
    with pytest.raises(ValueError):
        verify_raw(raw, ["A"], raw["chunks"], mandatory_setup_start_ns=0, proposal=no_action)
