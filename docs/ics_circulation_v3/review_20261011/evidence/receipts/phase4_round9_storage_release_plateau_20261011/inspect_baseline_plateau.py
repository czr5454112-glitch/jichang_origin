"""Instrument only old product-heap pops, without changing its priority."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import pickle
import sys
import time

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUT = BASE / "plateau_inspection_001.json"
if OUT.exists():
    raise FileExistsError("retain evidence")
cpu, wall = time.process_time(), time.perf_counter()
path = BASE / "baseline_001/storage_routing.py"
name = "scripts.experiments.ics_circulation_v3._frozen_storage_plateau"
spec = importlib.util.spec_from_file_location(name, path)
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
state = pickle.loads((BASE / "baseline_001/query_state.pickle").read_bytes())
saved = pickle.loads((BASE / "baseline_001/query_generator.pickle").read_bytes())
owner = module.StorageCandidateGenerator(deepcopy(saved.generator))
pops, by_f, by_stage, by_node = [], Counter(), Counter(), Counter()
original_pop = module.heappop
def recording_pop(queue):
    value = original_pop(queue)
    by_f[value[0]] += 1
    by_stage[str(value[4])] += 1
    by_node[value[2]] += 1
    if len(pops) < 20:
        pops.append({"f": value[0], "node": value[2], "tick": value[3], "visited": value[4], "leg_count": len(value[5])})
    return value
module.heappop = recording_pop
candidates = owner.generate(state, "projected:1x:2", "proxy-initial-26", 4)
result = dict(status=owner.last_search_status, expansions=owner.last_expansions,
              candidates=[asdict(c) for c in candidates], f_pop_counts=dict(by_f),
              visited_pop_counts=dict(by_stage), node_pop_counts=dict(by_node),
              first20=pops, physical_continuations=0, standalone_queries=1,
              frozen_source_sha256=sha256(path.read_bytes()).hexdigest(),
              cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall)
OUT.write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in {"node_pop_counts","first20"}}, indent=2))
