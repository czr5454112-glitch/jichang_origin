"""Retained old/new hand graphs, including an unresolved low-bound plateau."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import runpy
import sys
import time

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUT = BASE / "synthetic_comparison_001.json"
if OUT.exists():
    raise FileExistsError("retain all attempts")
cpu, wall = time.process_time(), time.perf_counter()
from scripts.experiments.ics_circulation_v3.model import Edge, Leg, Node, RouteCandidate, Tray
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, candidate_reservations
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
helpers = runpy.run_path(str(ROOT / "tests/test_ics_circulation_v3_storage_routing.py"))
path = BASE / "baseline_001/storage_routing.py"
spec = importlib.util.spec_from_file_location("scripts.experiments.ics_circulation_v3._old_plateau", path)
old_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old_module
spec.loader.exec_module(old_module)
rows = []
for busy in (False, True):
    state = helpers["case"](release=10000, deadline=12000, protected=True)
    state.network.edges.clear()
    for n in range(100):
        node = f"B{n:03d}"
        state.network.nodes[node] = Node(node, "zone", "owner")
        for key, source, target in ((f"a{n:03d}", "S", node), (f"b{n:03d}", node, "S")):
            state.network.edges[key] = Edge(key, source, target, 1)
    state.network.edges.update({"z-in": Edge("z-in", "S", "E", 1), "z-out": Edge("z-out", "E", "G", 1)})
    if busy:
        state.network.nodes["Q"] = Node("Q", "zone", "owner")
        state.network.edges["blocker-exit"] = Edge("blocker-exit", "E", "Q", 1)
        state.trays["blocker"] = Tray("blocker", "E")
        plan = RouteCandidate("blocker-plan", None, "blocker", (Leg("blocker-exit", 10002, 10003),),
                              10003, 10003, state.version, "blocker-plan", True, "Q")
        state.reservations += candidate_reservations(state, plan)
        state.plans["blocker"] = plan
        # A later fully legal witness exists even though its lower f lies
        # beyond many calendar-blind loop labels. The bounded tie fix does
        # not claim to solve that separate lower-bound weakness.
        feasible = RouteCandidate("later", "bag", "tray", (Leg("z-in", 10001, 10002), Leg("z-out", 10002, 10003)),
                                  10004, 10004, state.version, "later", True, "G")
        assert ExecutionValidator().validate(state, feasible).accepted
    for label, cls in (("old_fifo", old_module.StorageCandidateGenerator), ("new_static_remaining", StorageCandidateGenerator)):
        planner = cls(RegionalCandidateGenerator(horizon=10005, expansion_limit=500, deadline_ms=None, dynamic_local=True))
        before = deepcopy(state)
        q_cpu, q_wall = time.process_time(), time.perf_counter()
        candidates = planner.generate(state, "bag", "tray", 1)
        measured_cpu, measured_wall = time.process_time()-q_cpu, time.perf_counter()-q_wall
        assert state == before and all(ExecutionValidator().validate(state,c).accepted for c in candidates)
        rows.append(dict(case="busy_storage" if busy else "free_storage", version=label,
            candidates=[asdict(c) for c in candidates], status=planner.last_search_status,
            expansions=planner.last_expansions, diagnostics=planner.last_diagnostics,
            query_cpu_seconds=measured_cpu, query_wall_seconds=measured_wall))
assert not rows[0]["candidates"] and len(rows[1]["candidates"]) == 1
assert not rows[2]["candidates"] and not rows[3]["candidates"]
result = dict(status="passed", rows=rows, standalone_queries=4, physical_continuations=0,
              cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall,
              qualification="tie-break repairs an equal-f scheduling failure; busy calendar low-f plateau remains bounded unknown")
OUT.write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k!="rows"}, indent=2))
print(json.dumps([{k:r[k] for k in ("case","version","status","expansions")} for r in rows], indent=2))
