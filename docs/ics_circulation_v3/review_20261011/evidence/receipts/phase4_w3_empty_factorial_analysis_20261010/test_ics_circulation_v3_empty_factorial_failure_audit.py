"""Retain completed physics when only frozen-artifact verification fails."""
from copy import deepcopy
import gzip
from hashlib import sha256
import json

from scripts.experiments.ics_circulation_v3 import run_empty_factorial as runner


def test_artifact_mismatch_preserves_full_completed_physics(tmp_path, monkeypatch):
    old_dir = tmp_path / "old"
    (old_dir / "cases").mkdir(parents=True)
    output = tmp_path / "current"
    (output / "cases").mkdir(parents=True)
    record = {
        "metrics": {"status": "controller_quiescent", "completed": 1, "process_cpu_seconds": 0.25},
        "endpoints": {end: {"result": {"policy_stats": {}, "trace": [{"time": 3, "event": "completed"}],
                         "completion_times": {"bag": 3}}} for end in ("h80", "final")},
        "route_history": [{"time": 1, "choice": 0}],
        "slow_history": [{"trigger_time": 0, "proposals": []}],
    }
    old = deepcopy(record)
    old["endpoints"]["final"]["result"]["completion_times"]["bag"] = 4
    with gzip.open(old_dir / "cases" / "s0_t0_empty12_h40.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(old, stream)
    monkeypatch.setattr(runner, "OLD", old_dir)
    monkeypatch.setattr(runner, "sources", lambda: {"frozen": "hash"})
    monkeypatch.setattr(runner, "deploy", lambda *args: deepcopy(record))

    row = runner.worker(str(output), 0, 0, 0, {"frozen": "hash"})
    path = output / "cases" / row["file"]
    saved = json.loads(gzip.decompress(path.read_bytes()))
    assert row["status"] == saved["metrics"]["status"] == "artifact_verification_failure"
    assert saved["endpoints"] == record["endpoints"]
    assert saved["route_history"] == record["route_history"]
    assert saved["slow_history"] == record["slow_history"]
    assert saved["metrics"]["completed"] == 1
    assert saved["original_default_reproduction"]["equal"] == {
        "h80": True, "final": False, "route_history": True, "slow_actions": True}
    assert saved["failure"]["type"] == "ValueError"
    assert sha256(path.read_bytes()).hexdigest() == row["sha256"]
    assert row["invocation_cpu_seconds"] >= saved["invocation_cpu_before_gzip"] >= 0


def test_real_deploy_exception_is_separate_and_keeps_failure_accounting(tmp_path, monkeypatch):
    (tmp_path / "cases").mkdir()
    monkeypatch.setattr(runner, "sources", lambda: {"frozen": "hash"})

    def fail(*args):
        raise RuntimeError("injected deploy failure")

    monkeypatch.setattr(runner, "deploy", fail)
    row = runner.worker(str(tmp_path), 0, 0, 0, {"frozen": "hash"})
    path = tmp_path / "cases" / row["file"]
    saved = json.loads(gzip.decompress(path.read_bytes()))
    assert row["status"] == saved["metrics"]["status"] == "execution_failure"
    assert "endpoints" not in saved and "original_default_reproduction" not in saved
    assert saved["metrics"]["scheduled"] == 6
    assert saved["metrics"]["process_cpu_seconds"] >= 0
    assert saved["failure"]["type"] == "RuntimeError"
    assert "injected deploy failure" in saved["failure"]["traceback"]
    assert sha256(path.read_bytes()).hexdigest() == row["sha256"]
