from dataclasses import replace
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    BudgetFactory, BudgetGenerator, SearchBudget, SearchBudgetExceeded, bind_accounting,
    eligible_cell, network_futures, observed_role, validate_tape)
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, Simulation


def state():
    network = Network({n: Node(n, "z", "p", 2) for n in ("L", "J", "U")},
        {"LJ": Edge("LJ", "L", "J", 2), "JU": Edge("JU", "J", "U", 2)})
    return Snapshot(5, network, {"tray": Tray("tray", "L", "loaded", "seen")},
        {"seen": Bag("seen", "L", "U", 1, 20)})


def test_network_stress_preserves_valid_directed_od_identity_permissions_and_slack():
    snapshot = state()
    nominal = (snapshot.bags["seen"], Bag("future:0", "L", "U", 6, 21, True),
               Bag("future:1", "J", "U", 20, 40))
    tapes = network_futures(nominal, snapshot, count=32, seed=901)
    assert tapes == network_futures(nominal, snapshot, count=32, seed=901)
    by_id = {b.bag_id: b for b in nominal}
    assert len({tuple(b.bag_id for b in tape) for tape in tapes}) > 1
    for tape in tapes:
        validate_tape(tape, snapshot)
        assert len({b.bag_id for b in tape}) == len(tape)
        for bag in tape:
            original = by_id[bag.bag_id]
            assert bag.bag_id not in snapshot.bags and bag.arrival > snapshot.now
            assert (bag.origin, bag.destination, bag.protected) == (original.origin, original.destination, original.protected)
            assert bag.deadline - bag.arrival == original.deadline - original.arrival
    assert any(b.arrival == 6 for tape in tapes for b in tape)


@pytest.mark.parametrize("bag", [Bag("reverse", "U", "L", 8, 20),
    Bag("bad", "L", "missing", 8, 20), Bag("bad", "L", "U", 8, 7),
    Bag("bad", "L", "U", 8.5, 20), Bag("bad", "L", "U", 8, 20, 1)])
def test_invalid_or_unreachable_task_is_rejected_not_repaired(bag):
    with pytest.raises(ValueError):
        network_futures((bag,), state(), count=1, seed=0)


def test_real_role_cells_keep_zero_first_attempt_and_do_not_fabricate_arrival():
    snapshot = state()
    tray = snapshot.trays["tray"]
    assert observed_role(snapshot, tray) == "origin"
    assert observed_role(snapshot, replace(tray, node="J")) == "continuation"
    assert observed_role(snapshot, replace(tray, node="U")) == "arrival_at_destination"
    row = {"time": 6, "role": "continuation", "protected": False, "candidate_count": 0}
    used = set()
    cell = eligible_cell(row, used)
    assert cell == ("continuation", 0)
    used.add(cell)
    assert eligible_cell({**row, "time": 7, "candidate_count": 4}, used) is None
    assert eligible_cell({**row, "time": 42}, used) == ("continuation", 40)
    assert eligible_cell({**row, "protected": True, "time": 82}, used) is None


def test_checkpoint_clone_freezes_factory_accounting_and_rebinding_keeps_inner_state():
    engine = CursorSimulation.from_base_checkpoint(Simulation(state(), generator_factory=CandidateGenerator,
        reactive_empty_dispatch=False).checkpoint())
    accounting = bind_accounting(engine, SearchBudget(3, 10000, 10))
    generator = engine._generator.generator
    pending = engine.checkpoint().clone()
    engine._generator.generate(engine.state, "seen", "tray", 1)
    assert len(accounting.rows) == 1
    assert pending.base.generator_factory.owner.rows == []
    restored = CursorSimulation.from_checkpoint(pending)
    old_inner = restored._generator.generator
    rebound = bind_accounting(restored, SearchBudget(1, 10000, 10))
    assert restored._generator.generator is old_inner
    assert isinstance(restored.generator_factory, BudgetFactory)
    assert not isinstance(restored.generator_factory.inner_factory, BudgetFactory)
    restored._generator.generate(restored.state, "seen", "tray", 1)
    with pytest.raises(SearchBudgetExceeded, match="search_call_cap"):
        restored._generator.generate(restored.state, "seen", "tray", 1)
    assert generator is engine._generator.generator and len(rebound.rows) == 1


def test_branch_failure_and_call_cap_preserve_all_requested_rows_and_summary(tmp_path, monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_network_role_labels as runner
    monkeypatch.setattr(runner, "SOURCES", ("run_network_role_labels.py",))
    snapshot = state()
    future = (Bag("future", "L", "U", 10, 30),)
    monkeypatch.setattr(runner, "load_network", lambda profile: (snapshot.network, {}))
    monkeypatch.setattr(runner, "make_workload", lambda name, *a, **k: SimpleNamespace(name=name,
        initial=snapshot, forecasts=(), future_bags=future, horizon=40, provenance={}))
    def collect(scene, **kwargs):
        sample = {"identity": scene.name + ":d0", "time": 5, "source_node": "J", "role": "continuation",
            "band": 0, "candidate_count": 2, "checkpoint": SimpleNamespace(state=snapshot), "pool": ("a", "b")}
        return {"metadata": {"scene": scene.name, "status": "reached_horizon", "search_calls": 0,
                "search_work": 0, "failure": None}, "samples": [sample], "opportunities": [], "result": None}
    monkeypatch.setattr(runner, "collect_network_decisions", collect)
    monkeypatch.setattr(runner, "sample_artifact", lambda sample: {"identity": sample["identity"]})
    out = tmp_path / "output"
    def fail(*args, **kwargs):
        assert (out / "protocol.json").is_file()
        return {"status": "execution_failure", "result": None, "search_calls": 0,
            "search_work": 0, "wall_seconds": 0., "cpu_seconds": 0.,
            "failure": {"type": "RuntimeError", "message": "injected late failure"}}
    monkeypatch.setattr(runner, "branch_network_decision", fail)
    profile = tmp_path / "profile.json"
    profile.write_text("{}")
    result = runner.run(out, profile=profile, max_branch_calls=1)
    assert result["actual_full_simulator_calls"] == 1
    assert result["requested_branch_rows"] == 12
    assert result["branch_status_counts"] == {"execution_failure": 1, "not_executed": 11}
    assert len(result["failures"]) == 1 and (out / "summary.json").is_file()
    assert all(row.get("total_cost") is None for row in result["branches"])
    with pytest.raises(ValueError, match="cannot be overwritten"):
        runner.run(out, profile=profile)


def test_formal_mode_requires_declared_positive_evaluation_window(tmp_path):
    from scripts.experiments.ics_circulation_v3.run_network_role_labels import run
    with pytest.raises(ValueError, match="explicit evaluation horizon"):
        run(tmp_path / "new", mode="labels")
    assert not (tmp_path / "new").exists()


def test_actual_continuation_checkpoint_replays_after_unrelated_global_cache_changes():
    from scripts.experiments.ics_circulation_v3.network_role_labels import (
        branch_network_decision, collect_network_decisions)
    from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec
    from scripts.experiments.ics_circulation_v3.role_coverage import checkpoint_fingerprint
    from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator, clear_static_cache
    snapshot = state()
    scene = SimpleNamespace(name="directed_test_only", initial=snapshot, forecasts=(), future_bags=(), horizon=15)
    spec = ControlSpec(planning_horizon=20, predictive=False, reactive=False)
    collection = collect_network_decisions(scene, spec=spec, budget=SearchBudget(30, 10000, 10), bands=(0,))
    assert collection["metadata"]["status"] == "reached_horizon"
    sample = next(s for s in collection["samples"] if s["role"] == "continuation")
    assert sample["source_node"] == "J" and sample["checkpoint"].cursor.pending_tray_id == "tray"
    before = checkpoint_fingerprint(sample["checkpoint"])
    one = branch_network_decision(sample["checkpoint"], sample["pool"][0], (), horizon_ticks=8)
    clear_static_cache()
    RegionalCandidateGenerator(deadline_ms=None).generate(snapshot, "seen", "tray", 4)
    two = branch_network_decision(sample["checkpoint"], sample["pool"][0], (), horizon_ticks=8)
    assert one["status"] == two["status"] == "reached_horizon"
    assert one["result"].trace == two["result"].trace
    assert one["result"].final_snapshot == two["result"].final_snapshot
    assert one["result"].cost_components == two["result"].cost_components
    assert one["searches"] == two["searches"]
    assert one["cache_before"] == two["cache_before"] == sample["routing_cache"]
    assert checkpoint_fingerprint(sample["checkpoint"]) == before


def test_exact_memo_keeps_candidate_and_sample_boundaries_and_reuses_after_budget(tmp_path, monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_network_role_labels as runner
    monkeypatch.setattr(runner, "SOURCES", ("run_network_role_labels.py",))
    snapshot = state()
    monkeypatch.setattr(runner, "load_network", lambda profile: (snapshot.network, {}))
    monkeypatch.setattr(runner, "make_workload", lambda name, *a, **k: SimpleNamespace(name=name,
        initial=snapshot, forecasts=(), future_bags=(), horizon=40, provenance={}))
    def collect(scene, **kwargs):
        sample = {"identity": scene.name + ":d0", "time": 5, "source_node": "J", "role": "continuation",
            "band": 0, "candidate_count": 2, "checkpoint": SimpleNamespace(state=snapshot), "pool": ("a", "b")}
        return {"metadata": {"scene": scene.name, "status": "reached_horizon", "search_calls": 0,
                "search_work": 0, "failure": None}, "samples": [sample], "opportunities": [], "result": None}
    monkeypatch.setattr(runner, "collect_network_decisions", collect)
    monkeypatch.setattr(runner, "sample_artifact", lambda sample: {"identity": sample["identity"]})
    calls = []
    def branch(checkpoint, candidate, tape, **kwargs):
        calls.append(candidate)
        return {"status": "reached_horizon", "result": Simulation(snapshot).result(), "failure": None,
                "search_calls": 2, "search_work": 5, "wall_seconds": 0., "cpu_seconds": 0.}
    monkeypatch.setattr(runner, "branch_network_decision", branch)
    profile = tmp_path / "profile.json"
    profile.write_text("{}")
    one = runner.run(tmp_path / "capped", profile=profile, mode="labels", evaluation_horizon=80, max_branch_calls=1)
    assert calls == ["a"]
    assert one["requested_branch_rows"] == 192
    assert one["actual_full_simulator_calls"] == 1 and one["cache_reused_branches"] == 31
    assert one["branch_status_counts"] == {"reached_horizon": 32, "not_executed": 160}
    calls.clear()
    all_rows = runner.run(tmp_path / "complete", profile=profile, mode="labels", evaluation_horizon=80)
    assert calls == ["a", "b", "a", "b", "a", "b"]
    assert all_rows["actual_full_simulator_calls"] == 6 and all_rows["cache_reused_branches"] == 186
    assert all_rows["search_calls_collection_and_branches"] == 12


def test_parallel_scene_budget_and_worker_failure_keep_planned_denominator(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from scripts.experiments.ics_circulation_v3 import run_network_role_labels as runner
    monkeypatch.setattr(runner, "ProcessPoolExecutor", ThreadPoolExecutor)
    monkeypatch.setattr(runner, "SOURCES", ("run_network_role_labels.py",))
    calls = []
    def worker(args):
        name, output, profile, horizon, cpu, wall = args
        calls.append((name, horizon, cpu, wall))
        assert horizon == 80 and cpu == 2400 and wall == 3600
        if name == "counterflow":
            raise RuntimeError("worker crashed after retained partial output")
        output = Path(output)
        output.mkdir()
        runner.write_new_json(output / "manifest.json", {})
        return name, {"branches": [{"scene": name, "status": "not_executed", "cache_hit": False}],
            "actual_full_simulator_calls": 0, "cache_reused_branches": 0, "failures": [], "sampling_shortfalls": [],
            "source_changed_during_run": False, "cpu_seconds": 1., "wall_seconds": 2., "episodes": []}
    monkeypatch.setattr(runner, "_scene_worker", worker)
    profile = tmp_path / "profile.json"
    profile.write_text("{}")
    result = runner.run_parallel(tmp_path / "parallel", profile=profile)
    assert len(calls) == 3 and result["scene_count_planned"] == 3
    assert result["scene_summaries_received"] == 2 and not result["complete_resource_accounting"]
    assert result["worker_failures"][0]["scene"] == "counterflow"
    assert result["branch_status_counts"] == {"not_executed": 2}
    assert (tmp_path / "parallel" / "summary.json").is_file()
