"""Pure-data guards for the original-graph protocol runner; no native execution."""
from copy import deepcopy
import argparse
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation.run_original_protocol import (
    HORIZON, add_protocol_contract, assess_execution, execute_policy, expected_digest,
    final_diagnostics, paired_comparisons, request_ledger)
from scripts.experiments.g31_ics_circulation import run_original_protocol as runner


def test_shared_protocol_addition_preserves_every_physical_and_permission_field():
    original = {"jobs": [{"business_bag_id": "bag", "protected_service": True,
                          "allow_suffix_reroute": False, "storage_node": 12}],
                "trays": [{"tray_id": "fixed", "node": 3}], "node_contracts": [{"node": 3, "capacity": 1}],
                "edge_records": [(3, 12, 15, 2)], "options": {"max_events": 100000}}
    before = deepcopy(original)
    augmented = add_protocol_contract(original)
    assert original == before
    assert {k: v for k, v in augmented.items() if k != "owner_protocol"} == original
    assert not augmented["jobs"][0]["allow_suffix_reroute"]
    with pytest.raises(ValueError, match="existing_communication"):
        add_protocol_contract(augmented)


def make_call(*, retry=False):
    return {"at": 2. if retry else 0., "retry": retry, "kind": "transfer",
            "request": {"request_id": "owned", "owner_id": "A", "destination": 5}, "reply": {"status": "pending"}}


def test_lost_ack_is_unknown_and_retry_has_one_identity():
    calls = [make_call(), make_call(retry=True)]
    ledger = request_ledger(calls, {"A": {"now": 5., "delivered_transfer_acks": []}})
    assert ledger["request_count"] == 1 and ledger["retry_calls"] == 1
    assert ledger["requests_without_delivered_ack"] == 1
    assert ledger["requests"][0]["physical_received_at"] is None
    assert ledger["requests"][0]["resolution_without_ack"] == "unknown"


def test_retry_cannot_silently_change_transfer_payload():
    retry = make_call(retry=True)
    retry["request"]["destination"] = 6
    with pytest.raises(ValueError, match="retry_changed_payload"):
        request_ledger([make_call(), retry], {})


def test_received_event_time_comes_from_actual_delivered_snapshot():
    ack = {"request_id": "owned", "sequence": 2, "status": "received", "received_at": 3., "delivered_at": 4.}
    old = dict(ack, sequence=1, status="granted", received_at=-1., delivered_at=2.)
    ledger = request_ledger([make_call()], {"A": {"now": 5., "delivered_transfer_acks": [ack, old]}})
    assert ledger["requests"][0]["physical_received_at"] == 3.
    assert ledger["requests"][0]["last_delivered_ack"]["sequence"] == 2
    with pytest.raises(ValueError, match="undelivered_ack"):
        request_ledger([make_call()], {"A": {"now": 3.5, "delivered_transfer_acks": [ack]}})


@pytest.mark.parametrize("result", [None, {"horizon": 3600., "physical_clock": 3600.,
    "advance": {"status": "reached", "physical_time": 3600., "horizon_complete": True}}])
def test_budget_prefix_never_becomes_full_horizon_metrics(result):
    data = {"jobs": [{"business_bag_id": f"b{i}", "arrival": 6000.+i} for i in range(24)]}
    row = assess_execution(data, {"status": "wall_budget_exhausted", "result": result},
                           SimpleNamespace(physical_time=3600.))
    assert row["status"] == "unknown" and row["metrics"] is None
    assert row["declared_offered"] == 24
    assert len(row["declared_business_ids"]) == 24


def test_total_cost_tie_cannot_pass_strict_paired_protection():
    def metrics(values):
        return {"horizon": HORIZON, "cost": sum(values), "per_job": [
            {"business_bag_id": f"b{i}", "restricted_time": v, "status": "completed",
             "deadline_violated_by_horizon": False} for i, v in enumerate(values)]}
    cases = {"reactive_r2": {"metrics": metrics([5., 5.])},
             "predictive_r2": {"metrics": metrics([4., 6.])}, "joint_r1_r2": {"metrics": None}}
    comparison = paired_comparisons(cases)
    assert comparison["predictive_r2__vs__reactive_r2"]["cost_delta"] == 0
    assert comparison["predictive_r2__vs__reactive_r2"]["preserved"] is False
    assert comparison["joint_r1_r2__vs__predictive_r2"]["preserved"] is None


def test_frozen_binary_argument_requires_exact_sha256():
    assert expected_digest("AF"*32) == "af"*32
    for invalid in ("unknown", "f"*63, "g"*64):
        with pytest.raises(argparse.ArgumentTypeError):
            expected_digest(invalid)


def test_partial_tick_does_not_trigger_final_observation_or_recovery():
    class NoNativeMethodsPermitted:
        def __getattr__(self, key):
            raise AssertionError(f"incomplete tick touched native method {key}")
    result = final_diagnostics(NoNativeMethodsPermitted(), ["A", "B"], {"status": "unknown"}, [])
    assert result["status"] == "not_read_incomplete_execution"
    assert result["views"] is None and result["offline_final_state_sha256"] is None


def test_controller_budget_failure_stops_at_first_segment_without_resume(monkeypatch):
    session = SimpleNamespace(physical_time=0.)
    horizons = []
    def protocol(_session, _owners, *, horizon, **_kwargs):
        horizons.append(horizon)
        session.physical_time = horizon
        return {"status": "budget_exhausted", "result": None,
            "controller_state": {"control_boundary_complete": False},
            "control_continuation": {"status": "budget_exhausted"},
            "control_records": [], "client_calls": [], "native_batches": []}
    monkeypatch.setattr(runner, "run_protocol_control", protocol)
    run = execute_policy(session, ["A"], {})
    assert horizons == [3600.]
    assert run["status"] == "budget_exhausted" and run["result"] is None
    assert not run["controller_state"]["control_boundary_complete"]


def test_controller_exception_retains_prior_segments_without_pricing_prefix(monkeypatch):
    session = SimpleNamespace(physical_time=0.)
    call = make_call()
    def protocol(_session, _owners, *, horizon, **_kwargs):
        if horizon > 3600.:
            session.physical_time = 3601.
            raise ValueError("deliberate-orchestration-error")
        session.physical_time = horizon
        return {"status": "reached", "result": {"horizon": horizon},
            "controller_state": {"control_boundary_complete": True},
            "control_continuation": {"status": "reached"},
            "control_records": [], "client_calls": [call], "native_batches": []}
    monkeypatch.setattr(runner, "run_protocol_control", protocol)
    run = execute_policy(session, ["A"], {})
    assert run["status"] == "controller_exception"
    assert run["client_calls"] == [call] and run["result"]["horizon"] == 3600.
    assert len(run["segments"]) == 2
    assert "deliberate-orchestration-error" in run["segments"][1]["exception"]
    row = assess_execution({"jobs": [{"business_bag_id": "future", "arrival": 8000.}]}, run, session)
    assert row["status"] == "unknown" and row["metrics"] is None
    assert row["declared_offered"] == 1
