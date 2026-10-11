"""Freeze Round9 and exact real/synthetic query inputs before Round10 edits."""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import pickle
import runpy
import sys
import time
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUT = BASE / "baseline_001"
OUT.mkdir()
cpu, wall = time.process_time(), time.perf_counter()
report = dict(status="running", physical_continuations=0, standalone_queries=0, queries=[])
paths = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py"))
paths += [ROOT / "tests/test_ics_circulation_v3_storage_routing.py"]
before = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:
    target = OUT / "source_snapshot" / p.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(p.read_bytes())
report["source_sha256_before"] = before

def query(name, state, planner, bag_id, tray_id, k):
    directory = OUT / name
    directory.mkdir()
    (directory / "snapshot.pickle").write_bytes(pickle.dumps(state))
    (directory / "generator.pickle").write_bytes(pickle.dumps(planner))
    (directory / "snapshot.json").write_text(json.dumps(asdict(state), indent=2))
    qcpu, qwall = time.process_time(), time.perf_counter()
    report["standalone_queries"] += 1
    found = planner.generate(state, bag_id, tray_id, k)
    row = dict(name=name, bag_id=bag_id, tray_id=tray_id, k=k,
        horizon=planner.horizon, expansion_limit=planner.expansion_limit,
        cpu_seconds=time.process_time()-qcpu, wall_seconds=time.perf_counter()-qwall,
        status=planner.last_search_status, expansions=planner.last_expansions,
        diagnostics=planner.last_diagnostics, candidates=[asdict(c) for c in found])
    (directory / "query.json").write_text(json.dumps(row, indent=2))
    report["queries"].append(row)

try:
    from scripts.experiments.ics_circulation_v3.model import Edge, Leg, Node, RouteCandidate, Tray
    from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
    from scripts.experiments.ics_circulation_v3.runtime import Simulation, ExecutionValidator, candidate_reservations
    from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
    checkpoint_path = BASE.parent / "phase4_round9_storage_lifecycle_20261011/business_window_h21600_003/checkpoint_8400.pickle"
    raw = checkpoint_path.read_bytes()
    (OUT / "checkpoint_8400.pickle").write_bytes(raw)
    report["checkpoint_sha256"] = sha256(raw).hexdigest()
    report["physical_continuations"] += 1
    pcpu, pwall = time.process_time(), time.perf_counter()
    engine = Simulation.from_checkpoint(pickle.loads(raw))
    engine.advance(8881)
    state = engine.observe()
    report["continuation_cpu_seconds"] = time.process_time()-pcpu
    report["continuation_wall_seconds"] = time.perf_counter()-pwall
    target = "projected:1x:3"
    tray_id, = [t.tray_id for t in state.trays.values() if t.bag_id == target]
    (OUT / "checkpoint_8881.pickle").write_bytes(pickle.dumps(engine.checkpoint()))
    query("real_id3_8881", state, engine._generator, target, tray_id, engine.candidate_count)
    helpers = runpy.run_path(str(ROOT / "tests/test_ics_circulation_v3_storage_routing.py"))
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
            witnesses = []
            for arrival in (10000, 10002):
                feasible = RouteCandidate("later", "bag", "tray", (Leg("z-in", arrival-1, arrival), Leg("z-out", arrival, arrival+1)),
                    arrival+2, arrival+2, state.version, "later", True, "G")
                accepted = ExecutionValidator().validate(state, feasible).accepted
                assert accepted
                witnesses.append(dict(candidate=asdict(feasible), accepted=accepted))
            report["busy_known_witnesses"] = witnesses
        planner = StorageCandidateGenerator(RegionalCandidateGenerator(horizon=10005, expansion_limit=500, deadline_ms=None, dynamic_local=True))
        query("busy_storage" if busy else "free_storage", state, planner, "bag", "tray", 1)
    report["source_sha256_after"] = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in paths}
    assert report["source_sha256_before"] == report["source_sha256_after"]
    report["status"] = "passed"
except BaseException:
    report.update(status="failed", failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall,
        artifact_sha256={str(p.relative_to(OUT)):sha256(p.read_bytes()).hexdigest() for p in OUT.rglob("*") if p.is_file()},
        scope="source/input freeze + one partial physical checkpoint continuation + three queries; nested CPU is not additive")
    (OUT / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256_before','source_sha256_after','artifact_sha256','queries','busy_known_witnesses')},indent=2))
    print(json.dumps([{k:r[k] for k in ('name','status','expansions','cpu_seconds')} for r in report['queries']],indent=2))
sys.exit(0 if report['status']=='passed' else 1)
