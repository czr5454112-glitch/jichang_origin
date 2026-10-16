"""Persisted raw shards and replay budgets without loading a native binary."""
import gzip
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import profile_request_bundles as driver


@pytest.mark.parametrize("native_cut", [False, True])
def test_worker_streams_every_raw_part_and_replays_requested_budget(tmp_path, monkeypatch, native_cut):
    profile, output = tmp_path/"profile", tmp_path/"output"
    profile.mkdir(); output.mkdir()
    driver.atomic(profile/"input.json.gz", {"options": {"max_simulation_time": 20.}, "jobs": []}, compressed=True)
    driver.atomic(profile/"run.json.gz", {"controller_state": {"config": {"owners": ["A"]}},
                  "control_records": [{"old_diagnostic_only": True}]}, compressed=True)
    binary = tmp_path/"fake.pyd"; binary.write_bytes(b"not loaded")
    all_limits = []
    class Session:
        def __init__(self, data):
            self.physical_time = 0.
        def offline_state_sha256(self):
            return "same"
    def execute(session, owners, *, max_activations, state=None, **kwargs):
        assert max_activations > 0
        all_limits.append(max_activations)
        count = 0 if native_cut else max_activations
        epoch = 0 if state is None else state["epoch"]
        session.physical_time += count
        return {"status": "native_budget_exhausted" if native_cut else "control_budget_exhausted",
            "controller_state": {"epoch": epoch+count},
            "control_records": [{"owner_epoch": epoch+i, "compute_wall_ms": 1.} for i in range(count)],
            "client_calls": [], "native_batches": [{"timestamp_complete": False, "wall_ms": 1.}],
            "result": None, "control_continuation": {"physical_time": session.physical_time}}
    class Recorder:
        def __init__(self, session):
            self.session = session
        def run(self, owners, **kwargs):
            return execute(self.session, owners, **kwargs)
        def ledger(self):
            return {"saved": True}
    monkeypatch.setattr(driver, "load_native", lambda path: SimpleNamespace(NativeSession=Session))
    monkeypatch.setattr(driver, "BundleRecorder", Recorder)
    monkeypatch.setattr(driver, "run_event_protocol_control", execute)
    monkeypatch.setattr(driver, "analyze_bundles", lambda ledger: {
        "status": "complete_conservative_bundle_accounting", "requests": [], "exclusive_controller_wall_ns": 0})
    args = SimpleNamespace(output=output, profile=profile, binary=binary,
        expected_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), horizon=20.,
        max_activations=5, activation_shard_budget=2, event_budget=10, verify_uninstrumented=True)
    assert driver.worker(args) == 0
    expected = [2] if native_cut else [2, 2, 1]
    assert all_limits == expected+expected
    shards = sorted(output.glob("segment_*.json.gz"))
    assert len(shards) == len(expected)
    with gzip.open(shards[-1], "rt") as stream:
        raw = json.load(stream)
    assert raw["native_batches"][0]["timestamp_complete"] is False
    manifest = json.loads((output/"manifest.json").read_text())
    assert manifest["requested_activation_limits"] == expected
    assert all(manifest["uninstrumented_equivalence"].values())
    assert manifest["complete_declared_horizon"] is False
