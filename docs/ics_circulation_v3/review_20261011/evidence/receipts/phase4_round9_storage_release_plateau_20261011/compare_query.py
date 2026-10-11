"""Compare the fixed query at the exact retained pre-fix physical boundary."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import pickle
import runpy
import sys
import time

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUT = BASE / "comparison_001"
OUT.mkdir()
cpu, wall = time.process_time(), time.perf_counter()
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator
source = ROOT / "scripts/experiments/ics_circulation_v3/storage_routing.py"
before = sha256(source.read_bytes()).hexdigest()
(OUT / "storage_routing.py").write_bytes(source.read_bytes())
state_bytes = (BASE / "baseline_001/query_state.pickle").read_bytes()
state = pickle.loads(state_bytes)
saved = pickle.loads((BASE / "baseline_001/query_generator.pickle").read_bytes())
planner = StorageCandidateGenerator(deepcopy(saved.generator))
query_cpu, query_wall = time.process_time(), time.perf_counter()
candidates = planner.generate(state, "projected:1x:2", "proxy-initial-26", 4)
new = dict(query_cpu_seconds=time.process_time()-query_cpu, query_wall_seconds=time.perf_counter()-query_wall,
    status=planner.last_search_status, expansions=planner.last_expansions,
    diagnostics=planner.last_diagnostics, candidates=[asdict(c) for c in candidates],
    validation=[asdict(ExecutionValidator().validate(state, c)) for c in candidates])
assert candidates and all(v["accepted"] for v in new["validation"])
assert asdict(state) == asdict(pickle.loads(state_bytes))
assert planner.horizon == saved.horizon == 21600 and planner.expansion_limit == saved.expansion_limit == 10000
old = json.loads((BASE / "baseline_001/result.json").read_bytes())
assert new["diagnostics"]["static_lower_bound"] == old["diagnostics"]["static_lower_bound"]
assert new["diagnostics"]["work_units_by_stage"]["topology_edges"] == old["diagnostics"]["work_units_by_stage"]["topology_edges"]
assert new["diagnostics"]["work_units_by_stage"]["reverse_lower_bound"] == old["diagnostics"]["work_units_by_stage"]["reverse_lower_bound"]
assert all(c.unload_complete <= state.bags[c.bag_id].deadline for c in candidates)
assert sha256(source.read_bytes()).hexdigest() == before
result = dict(status="passed", source_sha256=before, query_state_sha256=sha256(state_bytes).hexdigest(),
    physical_continuations=0, standalone_queries=1, old_source_sha256=old["source_sha256_before"],
    old_status=old["search_status"], old_expansions=old["expansions"], new=new,
    same_budget_horizon_k=True, same_input_state=True, unchanged_preprocessing_units=True,
    cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall)
(OUT / "result.json").write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k!="new"}, indent=2))
print(json.dumps({k:v for k,v in new.items() if k not in {"candidates","validation"}}, indent=2))
