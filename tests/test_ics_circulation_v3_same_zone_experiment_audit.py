"""Independent failure injection for round6 retained physical evidence."""
from dataclasses import asdict
import json

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator
from scripts.experiments.ics_circulation_v3.same_zone_experiment import run_observed_cycle
from scripts.experiments.ics_circulation_v3 import run_same_zone_supply as runner


def _engine():
    network = Network({n: Node(n, "zone", "owner:" + n, 3) for n in "AB"},
        {"AB": Edge("AB", "A", "B", 2, 2), "BA": Edge("BA", "B", "A", 2, 2)})
    initial = Snapshot(0, network, {"tray": Tray("tray", "A", "loaded", "seen")},
                       {"seen": Bag("seen", "A", "B", 0, 20)})
    base = build_engine(initial, (), (), ControlSpec(planning_horizon=20))
    enable_replay_cache(base)
    return CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)


def test_forced_choice_exception_preserves_entry_state_and_has_execution_failure_status(monkeypatch):
    engine = _engine()
    candidate, = CandidateGenerator().generate(engine.state, "seen", "tray", k=1)
    before = asdict(engine.state)

    def injected(*_):
        raise ValueError("injected forced choice failure")

    monkeypatch.setattr(engine, "choose_pending", injected)
    result = run_observed_cycle(engine, {"seen"}, minimum_observation_at=10,
                                forced_candidate=candidate)
    assert result["status"] == "execution_failure"
    assert result["failure"]["message"] == "injected forced choice failure"
    assert result["initial_state"] == before
    assert result["expected_task_ids"] == ["seen"]
    assert result["result"] is None
    assert result["cpu_seconds"] >= 0


@pytest.mark.parametrize("phase", ["prior_comparison", "raw_serialization"])
def test_postphysical_failure_keeps_entire_outcome_and_partial_files(tmp_path, monkeypatch, phase):
    engine = _engine()
    candidate, = CandidateGenerator().generate(engine.state, "seen", "tray", k=1)
    marker = {"status": "controller_quiescent", "result": {"retained_marker": "actual physical result"},
              "original_endpoint": {"result": {}}, "searches": [{"time": 3, "work": 17}],
              "cpu_seconds": 0.125}
    row = {"case_id": "independent_failure", "scene": "counterflow", "candidate": 0,
           "policy": "old32" if phase == "prior_comparison" else "old64",
           "tape_id": "checkpoint_nominal", "kind": "checkpoint"}
    (tmp_path / "mechanism").mkdir()
    monkeypatch.setattr(runner, "verify", lambda *_: {})
    monkeypatch.setattr(runner, "restored_d40", lambda: (engine,
        {"pool": (candidate,), "future": ()},
        {"checkpoint_sha256": "checkpoint", "future_sha256": "future"}, {"all": True}))
    monkeypatch.setattr(runner, "install_supply_policy", lambda *_: {"policy": row["policy"]})
    monkeypatch.setattr(runner, "file_sha", lambda *_: "sha")
    monkeypatch.setattr(runner, "run_observed_cycle", lambda *_args, **_kwargs: marker)
    monkeypatch.setattr(runner, "case_metrics", lambda *_: {"status": "controller_quiescent"})

    if phase == "prior_comparison":
        def broken_read(*_):
            raise ValueError("injected prior comparison failure")
        monkeypatch.setattr(runner, "read", broken_read)
    else:
        def broken_write(path, *_):
            path.write_bytes(b"partial gzip retained")
            raise OSError("injected serialization failure")
        monkeypatch.setattr(runner, "write_gzip", broken_write)
    result = runner.run_case(tmp_path, "mechanism", row)
    assert result["status"] == "invocation_failure"
    assert result["actual_physical_call"] is True
    assert result["physical_result_status"] == "controller_quiescent"
    recovery_files = list((tmp_path / "mechanism").glob("*.recovery.json"))
    assert len(recovery_files) == 1
    recovery = json.loads(recovery_files[0].read_text(encoding="utf-8"))
    assert recovery["outcome"] == marker
    assert result["invocation_cpu_seconds"] >= 0
    if phase == "raw_serialization":
        assert (tmp_path / "mechanism/independent_failure.json.gz").read_bytes() == b"partial gzip retained"
