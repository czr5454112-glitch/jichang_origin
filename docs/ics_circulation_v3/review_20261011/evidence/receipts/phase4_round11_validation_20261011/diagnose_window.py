"""Fixed raw original-window backlog classification; no new simulation."""
from collections import Counter, defaultdict, deque
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
folder, output = BASE / sys.argv[1], BASE / sys.argv[2]
output.mkdir()
cpu, wall = process_time(), perf_counter()
bindings = {}


def read(path):
    data = path.read_bytes()
    bindings[path.relative_to(ROOT).as_posix()] = sha256(data).hexdigest()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data)


result = read(folder / "final_result.json.gz")
tape = read(folder / "environment_tape.json")
snapshot = result["final_snapshot"]
adj = defaultdict(list)
for edge in snapshot["network"]["edges"].values():
    if edge["capacity"] > 0:
        adj[edge["source"]].append(edge["target"])


def reachable(source, target):
    seen, queue = {source}, deque([source])
    while queue:
        current = queue.popleft()
        if current == target:
            return True
        for next_node in adj[current]:
            if next_node not in seen:
                seen.add(next_node)
                queue.append(next_node)
    return False


loaded = {event["bag_id"]: event["tray_id"] for event in result["trace"] if event["event"] == "load"}
rows = []
for bag in tape:
    bag_id = bag["bag_id"]
    via = bag["storage"]["node_id"]
    static = reachable(bag["origin"], via) and reachable(via, bag["destination"])
    tray_id = loaded.get(bag_id)
    status = "completed" if bag_id in result["completed"] else "loaded_unfinished" if tray_id else "not_loaded"
    rows.append({"bag_id": bag_id, "static_loaded_reachable": static, "status": status,
                 "tray_id": tray_id, "deadline": bag["deadline"],
                 "deadline_passed": snapshot["now"] > bag["deadline"],
                 "completion": result["completed"].get(bag_id)})
failures = []
query_path = folder / "queries.jsonl.gz"
bindings[query_path.relative_to(ROOT).as_posix()] = sha256(query_path.read_bytes()).hexdigest()
with gzip.open(query_path, "rt", encoding="utf-8") as stream:
    for line in stream:
        query = json.loads(line)
        if query["status"] == "expansion_budget_exhausted":
            failures.append({key: query[key] for key in ("now", "bag_id", "tray_id", "destination", "candidate_count", "expansions", "diagnostics")})
summary = Counter((row["static_loaded_reachable"], row["status"]) for row in rows)
report = {"status": "passed", "now": snapshot["now"], "full_window_count": len(tape), "rows": rows,
          "backlog_classes": [{"static_loaded_reachable": key[0], "status": key[1], "count": n} for key, n in summary.items()],
          "budget_exhausted_queries": failures, "physical_runs": 0,
          "cpu_seconds": process_time()-cpu, "wall_seconds": perf_counter()-wall, "input_sha256": bindings,
          "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
          "qualification": "Static path necessity and observed statuses only; no causal capacity/optimal-schedule proof"}
(output / "results.json").write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "budget_exhausted_queries", "input_sha256")}, indent=2))
print(json.dumps([{k: q[k] for k in ("now", "bag_id", "tray_id", "destination", "candidate_count", "expansions")} for q in failures], indent=2))
