"""The old envelope diagnostic must retain no-message work and input counts."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation.audit_request_measurement import diagnose


def sample():
    run = {"status": "control_budget_exhausted", "wall_seconds": .201,
        "control_records": [
            {"compute_wall_ms": 101., "publications": [], "service_actions": [{"kind": "route_not_proposed"}], "attempts": []},
            {"compute_wall_ms": 50., "publications": [{"request_id": "m"}], "service_actions": [], "attempts": []}],
        "native_batches": [{"wall_ms": 10.}],
        "controller_state": {"client": {"outbox": {"m": {}}}},
        "client_calls": [{"request": {"request_id": "m"}}]}
    summary = {"owner_activations": 2, "offered_total": 3, "status": run["status"], "wall_seconds": .201,
        "offered_by_current_time": 1, "physical_time": 5., "horizon": 100., "cprofile_enabled": True}
    return run, summary, {"jobs": [{}, {}, {}]}


def test_route_failure_without_message_remains_in_update_denominator():
    args = sample(); before = copy.deepcopy(args)
    report = diagnose(*args)
    assert report["owner_update_count"] == 2
    assert report["protocol_request_count"] == 1
    assert report["owner_updates_without_new_protocol_message"] == 1
    assert report["no_new_message_update_measured_over_100ms_count"] == 1
    assert report["global_unlocated_residual_ms"] == 40.
    assert report["complete_request_compute_measured"] is False
    assert report["complete_100ms_requirement_certified"] is False
    assert args == before


@pytest.mark.parametrize("defect", ["missing_activation", "missing_job", "missing_call", "negative_residual", "nonfinite"])
def test_inconsistent_trace_does_not_become_a_usable_diagnostic(defect):
    run, summary, data = sample()
    if defect == "missing_activation":
        run["control_records"].pop()
    elif defect == "missing_job":
        data["jobs"].pop()
    elif defect == "missing_call":
        run["client_calls"] = []
    elif defect == "negative_residual":
        run["control_records"][0]["compute_wall_ms"] = 1000.
    else:
        run["control_records"][0]["compute_wall_ms"] = float("nan")
    with pytest.raises(ValueError):
        diagnose(run, summary, data)
