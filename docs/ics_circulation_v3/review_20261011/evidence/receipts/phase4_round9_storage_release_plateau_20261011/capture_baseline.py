"""Retain exact pre-fix source and real query boundary before editing."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import pickle
import sys
import time
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUT = BASE / "baseline_001"
OUT.mkdir()
source = ROOT / "scripts/experiments/ics_circulation_v3/storage_routing.py"
before = sha256(source.read_bytes()).hexdigest()
(OUT / "storage_routing.py").write_bytes(source.read_bytes())
(OUT / "test_storage_routing.py").write_bytes((ROOT / "tests/test_ics_circulation_v3_storage_routing.py").read_bytes())
checkpoint_path = BASE.parent / "phase4_round9_storage_lifecycle_20261011/business_window_h21600_002/checkpoint_8400.pickle"
raw_checkpoint = checkpoint_path.read_bytes()
(OUT / "checkpoint_8400.pickle").write_bytes(raw_checkpoint)
cpu, wall = time.process_time(), time.perf_counter()
report = {"status": "running", "source_sha256_before": before,
          "source_checkpoint_sha256": sha256(raw_checkpoint).hexdigest(),
          "physical_continuations": 0, "standalone_queries": 0}
try:
    from scripts.experiments.ics_circulation_v3.runtime import Simulation
    checkpoint = pickle.loads(raw_checkpoint)
    report["physical_continuations"] += 1
    replay_cpu, replay_wall = time.process_time(), time.perf_counter()
    engine = Simulation.from_checkpoint(checkpoint)
    engine.advance(8876)
    state = engine.observe()
    report["continuation_cpu_seconds"] = time.process_time() - replay_cpu
    report["continuation_wall_seconds"] = time.perf_counter() - replay_wall
    target = "projected:1x:2"
    tray_id, = [t.tray_id for t in state.trays.values() if t.bag_id == target]
    (OUT / "query_state.pickle").write_bytes(pickle.dumps(state))
    (OUT / "query_generator.pickle").write_bytes(pickle.dumps(engine._generator))
    (OUT / "query_state.json").write_text(json.dumps(asdict(state), indent=2))
    (OUT / "checkpoint_8876.pickle").write_bytes(pickle.dumps(engine.checkpoint()))
    query_cpu, query_wall = time.process_time(), time.perf_counter()
    report["standalone_queries"] += 1
    candidates = engine._generator.generate(state, target, tray_id, engine.candidate_count)
    report.update(query_cpu_seconds=time.process_time()-query_cpu,
                  query_wall_seconds=time.perf_counter()-query_wall,
                  bag_id=target, tray_id=tray_id, k=engine.candidate_count,
                  horizon=engine._generator.horizon, expansion_limit=engine._generator.expansion_limit,
                  candidates=[asdict(c) for c in candidates],
                  search_status=engine._generator.last_search_status,
                  expansions=engine._generator.last_expansions,
                  diagnostics=engine._generator.last_diagnostics)
    report["source_sha256_after"] = sha256(source.read_bytes()).hexdigest()
    assert report["source_sha256_before"] == report["source_sha256_after"]
    report["status"] = "passed"
except BaseException:
    report.update(status="failed", failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall,
                  scope="module imports, one actual checkpoint continuation and one measured real-state query; query CPU nested")
    (OUT / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
sys.exit(0 if report["status"] == "passed" else 1)
