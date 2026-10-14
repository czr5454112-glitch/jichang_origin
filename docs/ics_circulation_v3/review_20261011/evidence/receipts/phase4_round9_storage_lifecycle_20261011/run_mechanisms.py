"""A fixed 10-case x 2-mode x (one run + two restored branches) census."""
import hashlib
import json
import pickle
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
cpu, wall = time.process_time(), time.perf_counter()
from scripts.experiments.ics_circulation_v3.storage_lifecycle import CASE_NAMES, mechanism, lifecycle_report
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.network_full_cycle import physical_result
from scripts.experiments.ics_circulation_v3.experiment_resources import memory_snapshot

output = BASE / (sys.argv[1] if len(sys.argv) > 1 else "mechanisms_001")
output.mkdir()
protocol = {"cases": sys.argv[2:] or CASE_NAMES, "modes": ["whole_route", "next_edge"],
    "pause_ticks": [1, 8], "stop_tick": 160, "tasks_per_case": 3,
    "research_proxy_only": True, "no_outcome_based_case_exclusions": True,
    "search_horizon": 80, "expansion_limit": 100000, "deadline_ms": None,
    "fixed_module": {"unload": 1, "hold_final": 2, "reception_capacity": 1},
    "no_metric_comparison_to_legacy_split_early_tasks": True}
(output / "protocol.json").write_text(json.dumps(protocol, indent=2))
paths = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py")) + [Path(__file__)]
def bindings():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before = bindings()
(output / "before.json").write_text(json.dumps(before, indent=2))
rows, started_runs, completed_runs = [], 0, 0
try:
    for case in protocol["cases"]:
        for mode in protocol["modes"]:
            started_runs += 1
            engine = mechanism(case, mode)
            checkpoints = []
            for pause in protocol["pause_ticks"]:
                engine.advance(pause)
                checkpoints.append(engine.checkpoint())
            final = engine.advance(protocol["stop_tick"])
            completed_runs += 1
            report = lifecycle_report(engine, ("early1", "early2", "direct"))
            report.update(case=case, mode=mode, checkpoint_replays=[])
            stem = f"{case}_{mode}"
            for checkpoint in checkpoints:
                checkpoint_path = output / f"{stem}_pause{checkpoint.state.now}.pickle"
                checkpoint_path.write_bytes(pickle.dumps(checkpoint))
                started_runs += 1
                replay = Simulation.from_checkpoint(checkpoint).advance(protocol["stop_tick"])
                completed_runs += 1
                replay_path = output / f"{stem}_replay{checkpoint.state.now}.json"
                replay_path.write_text(json.dumps(physical_result(replay), indent=2))
                exact = physical_result(final) == physical_result(replay)
                report["checkpoint_replays"].append({"at": checkpoint.state.now, "exact": exact,
                    "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
                    "replay_sha256": hashlib.sha256(replay_path.read_bytes()).hexdigest()})
                assert exact
            (output / (stem + ".json")).write_text(json.dumps(physical_result(final), indent=2))
            rows.append(report)
    outcome = {"success": True, "rows": rows}
except Exception:
    outcome = {"success": False, "rows": rows, "failure": traceback.format_exc()}
after = bindings()
outcome.update(physical_runs_started=started_runs, physical_runs_completed=completed_runs,
    source_changed=[p for p in before if before[p] != after[p]],
    cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall,
    memory=memory_snapshot(), cpu_scope="current process from before ICS imports through results/source checks, excluding final output writes")
(output / "after.json").write_text(json.dumps(after, indent=2))
(output / "results.json").write_text(json.dumps(outcome, indent=2))
print(json.dumps({k:v for k,v in outcome.items() if k != "rows"}, indent=2))
sys.exit(0 if outcome["success"] and not outcome["source_changed"] else 1)
