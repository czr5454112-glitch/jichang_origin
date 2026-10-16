from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import analytic_control
from scripts.experiments.g31_ics_circulation import full_day_sparse_pool as pooled
from scripts.experiments.g31_ics_circulation.public_travel_pool import PublicTravel
from scripts.experiments.g31_ics_circulation.validate_full_day_sparse_pool import compare_raw


def observation():
    return {"owner_id": "A", "now": 0., "node_records": [[0, 0, .1], [1, 0, .2]],
            "edge_records": [[0, 1, 1., 2.]], "edge_contracts": [], "known_faults": []}


@pytest.mark.parametrize("mode", ["on", "off"])
def test_wrapped_worker_receives_exact_same_arguments_and_restores_original(tmp_path, monkeypatch, mode):
    args = SimpleNamespace(output=tmp_path, travel_pool=mode, suite="full2x", horizon=86400.,
        event_budget=1000000, max_activations=1000000, activation_shard_budget=500, segment_seconds=3600.)
    before = deepcopy(vars(args))
    expected = PublicTravel(observation()).path(0, 1)
    def original_worker(actual):
        assert actual is args and vars(actual) == before
        assert (analytic_control.PublicTravel is PublicTravel) is (mode == "off")
        for owner in ("A", "A", "B"):
            view = observation(); view["owner_id"] = owner
            assert analytic_control.PublicTravel(view).path(0, 1) == expected
        return 0
    monkeypatch.setattr(pooled.sparse, "worker", original_worker)
    assert pooled.worker(args) == 0 and analytic_control.PublicTravel is PublicTravel and vars(args) == before
    diagnostics = json.loads((tmp_path / "travel_pool.json").read_bytes())
    assert diagnostics["mode"] == mode and diagnostics["persisted_in_controller_state"] is False
    if mode == "on":
        assert (diagnostics["checkouts"], diagnostics["graph_hits"], diagnostics["graph_misses"]) == (3, 1, 2)
    else:
        assert "graph_hits" not in diagnostics


def test_failed_controller_leaves_factory_restored_and_no_success_diagnostics(tmp_path, monkeypatch):
    def failed(args):
        analytic_control.PublicTravel(observation()).path(0, 1)
        raise RuntimeError("native failure")
    monkeypatch.setattr(pooled.sparse, "worker", failed)
    with pytest.raises(RuntimeError, match="native failure"):
        pooled.worker(SimpleNamespace(output=tmp_path, travel_pool="on"))
    assert analytic_control.PublicTravel is PublicTravel and not (tmp_path / "travel_pool.json").exists()


def test_unknown_mode_cannot_invoke_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(pooled.sparse, "worker", lambda args: pytest.fail("should not invoke"))
    with pytest.raises(ValueError, match="invalid_sparse_pool_mode"):
        pooled.worker(SimpleNamespace(output=tmp_path, travel_pool="unknown"))


@pytest.mark.parametrize("field", ["seal_missing", "seal_changed", "request", "order", "boundary", "state"])
def test_gate_keeps_seal_schedule_request_order_boundaries_and_checkpoint_exact(field):
    expected = {"native_state_sha256": "a" * 64, "diagnostic_seal_wall_ms": 1.,
        "client_calls": [{"submit_compute_ms": 1., "request": {"id": "one", "at": 1.}}],
        "native_batches": [{"start_at": 1., "end_at": 2.}], "controller_state": {"first": 1, "second": 2}}
    actual = deepcopy(expected)
    actual["diagnostic_seal_wall_ms"] = 2.
    actual["client_calls"][0]["submit_compute_ms"] = 2.
    compare_raw(actual, expected)
    if field == "seal_missing": del actual["native_state_sha256"]
    elif field == "seal_changed": actual["native_state_sha256"] = "b" * 64
    elif field == "request": actual["client_calls"][0]["request"]["at"] = 2.
    elif field == "order": actual["controller_state"] = {"second": 2, "first": 1}
    elif field == "boundary": actual["native_batches"][0]["end_at"] = 3.
    else: actual["controller_state"]["second"] = 3
    with pytest.raises(ValueError, match="ordered_raw_changed"):
        compare_raw(actual, expected)
