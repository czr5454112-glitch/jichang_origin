"""Additional-budget tail branch; replay exact original stop before continuation."""
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import pickle
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
cpu, wall = process_time(), perf_counter()
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.network_full_cycle import physical_result
from scripts.experiments.ics_circulation_v3.storage_lifecycle import lifecycle_report
from scripts.experiments.ics_circulation_v3.experiment_resources import memory_snapshot

source = BASE / sys.argv[1]
out = BASE / sys.argv[2]
out.mkdir()
paths = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py"))
paths += [ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp", Path(__file__)]


def bindings():
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths}


before = bindings()
(out / "before.json").write_text(json.dumps(before, indent=2))
for p in paths:
    target = out / "source_snapshot" / p.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(p.read_bytes())
report = {"success": False, "physical_runs_started": 0, "physical_runs_completed": 0,
          "scope": "additional-budget h21600 development continuation; not part of original 600 CPU budget comparison"}
engine = None
try:
    prior = json.loads((source / "results.json").read_bytes())
    assert prior["success"] and not prior["source_changed"] and prior["status"] in ("cpu_cap_censored", "wall_cap_censored")
    with gzip.open(source / "final_result.json.gz", "rt", encoding="utf-8") as stream:
        original = json.load(stream)
    stop = original["final_snapshot"]["now"]
    scope = json.loads((source / "scope.json").read_bytes())
    tail = scope["tail_cap_tick"]
    assert stop < tail == 28500
    checkpoint_path = max(source.glob("checkpoint_*.pickle"), key=lambda p: int(p.stem.split("_")[-1]))
    original_bindings = json.loads((source / "before.json").read_bytes())
    assert all(original_bindings[p] == value for p, value in before.items() if p != Path(__file__).relative_to(ROOT).as_posix())
    (out / "input_checkpoint.pickle").write_bytes(checkpoint_path.read_bytes())
    checkpoint = pickle.loads(checkpoint_path.read_bytes())
    assert checkpoint.state.now <= stop
    protocol = {"original_run": source.name, "original_stop": stop, "checkpoint_tick": checkpoint.state.now,
                "checkpoint_sha256": sha256(checkpoint_path.read_bytes()).hexdigest(),
                "original_result_sha256": sha256((source / "final_result.json.gz").read_bytes()).hexdigest(),
                "original_source_sha256": original_bindings, "additional_cpu_cap_seconds": 600,
                "additional_wall_cap_seconds": 900, "target_tick": tail, "outer_chunk_ticks": 60,
                "qualification": report["scope"]}
    (out / "protocol.json").write_text(json.dumps(protocol, indent=2))
    for filename in ("scope.json", "environment_tape.json", "full_window_source_tasks.json", "runtime_contract.json", "initial_snapshot.json"):
        (out / filename).write_bytes((source / filename).read_bytes())
    counts = Counter()
    with gzip.open(out / "queries.jsonl.gz", "wt", encoding="utf-8") as query_file:
        class MeteredSimulation(Simulation):
            def _generate(self, tray, destination=None):
                candidates = super()._generate(tray, destination)
                counts[self._generator.last_search_status] += 1
                query_file.write(json.dumps({"now": self.state.now, "tray_id": tray.tray_id,
                    "bag_id": tray.bag_id, "destination": destination,
                    "status": self._generator.last_search_status, "candidate_count": len(candidates),
                    "expansions": self._generator.last_expansions, "diagnostics": self._generator.last_diagnostics}) + "\n")
                return candidates
        engine = MeteredSimulation.from_checkpoint(checkpoint)
        report.update(physical_runs_started=1, initial_generation_calls=engine.policy_stats["generation_calls"])
        phys_cpu, phys_wall = process_time(), perf_counter()
        # Bridge is included in the one branch's budget, never counted twice.
        bridged = physical_result(engine.advance(stop))
        with gzip.open(out / "bridge_at_original_stop.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(bridged, stream)
        report.update(bridge_exact=bridged == original,
                      bridge_cpu_seconds_nested=process_time()-phys_cpu,
                      bridge_wall_seconds_nested=perf_counter()-phys_wall)
        assert report["bridge_exact"], "continuation must first reproduce original stopped result exactly"
        status = "fixed_tail_cap_censored"
        while engine.state.now < tail:
            if process_time()-phys_cpu >= 600:
                status = "additional_cpu_cap_censored"
                break
            if perf_counter()-phys_wall >= 900:
                status = "additional_wall_cap_censored"
                break
            engine.advance(min(tail, engine.state.now + 60))
            if engine.state.now % 600 == 0:
                (out / f"checkpoint_{engine.state.now}.pickle").write_bytes(pickle.dumps(engine.checkpoint()))
                print(json.dumps({"now": engine.state.now, "observed": len(engine.state.bags),
                    "completed": len(engine.state.completed), "cpu_s": process_time()-phys_cpu}), flush=True)
        (out / "final_checkpoint.pickle").write_bytes(pickle.dumps(engine.checkpoint()))
        report.update(success=True, status=status, physical_runs_completed=1,
                      lifecycle=lifecycle_report(engine, scope["all_window_ids"]), search_status_counts=dict(counts),
                      physics_cpu_seconds=process_time()-phys_cpu, physics_wall_seconds=perf_counter()-phys_wall)
except Exception:
    report.update(status="execution_failure", exception=traceback.format_exc())
finally:
    if engine is not None:
        with gzip.open(out / "final_result.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(physical_result(engine.result()), stream)
    after = bindings()
    report.update(source_changed=[p for p in before if before[p] != after[p]],
                  cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall, memory=memory_snapshot(),
                  resource_scope="parent including bridge/physics/source reads/raw serialization; nested intervals not additional; final writes excluded")
    (out / "after.json").write_text(json.dumps(after, indent=2))
    (out / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ("lifecycle", "search_status_counts")}, indent=2))
raise SystemExit(0 if report["success"] and not report["source_changed"] else 1)
