"""Real native budget truncation must never certify a finite reference."""
import os
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.analytic_control import run_online_matching
from scripts.experiments.g31_ics_circulation.finite_reference import Intervention, enumerate_interventions


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


@pytest.mark.parametrize("horizon", [20., .1])
@pytest.mark.parametrize("wrapper", ["envelope", "raw_result", "metadata_stripped"])
def test_actual_native_exhaustion_remains_unknown_through_continuation_wrappers(native, horizon, wrapper):
    data = tiny_cycle()
    data["transfers"] = []
    data["options"]["max_events"] = 5
    source = native.NativeSession(data)
    def continuation(branch, target):
        run = run_online_matching(branch, ["A", "B"], horizon=target, predictive=False, publish=False)
        if wrapper == "envelope":
            return run
        if wrapper == "metadata_stripped":
            run["result"].pop("control_continuation")
        return run["result"]
    reference = enumerate_interventions(source, [Intervention("WAIT", "wait"), Intervention("second", "wait")],
        horizon=horizon, job_contracts=data["jobs"], continuation=continuation,
        validate=lambda result, action: pytest.fail("native truncated prefix was incorrectly sent for full-horizon audit"))
    assert not reference["exhaustive"] and reference["optimality"] == "unknown"
    assert reference["best_action_id"] is None
    assert all(r["status"] == "incomplete_horizon" and "metrics" not in r for r in reference["rows"])


def test_real_complete_native_result_cannot_override_null_envelope_status(native):
    data = tiny_cycle()
    source = native.NativeSession(data)
    def continuation(branch, horizon):
        result = branch.result_at(horizon)
        assert result["advance"]["horizon_complete"] is True
        return {"status": None, "result": result}
    reference = enumerate_interventions(source, [Intervention("WAIT", "wait")], horizon=20.,
        job_contracts=data["jobs"], continuation=continuation,
        validate=lambda result, action: pytest.fail("null envelope reached full-horizon verification"))
    assert reference["optimality"] == "unknown" and not reference["exhaustive"]
