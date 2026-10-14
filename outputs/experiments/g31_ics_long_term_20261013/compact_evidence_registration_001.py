"""Register actual frozen compact-control results; never rerun physics here."""
import gzip
import hashlib
import json
from pathlib import Path

from scripts.experiments.g31_ics_circulation.analytic_control import demand_signature

root = Path.cwd()
base = root / "outputs/experiments/g31_ics_long_term_20261013"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
load = lambda p: json.loads(p.read_text(encoding="utf-8"))
old = base / "p2_original_mechanism_24_005_001"
new = base / "p2_original_mechanism_24_compact_007_001"
comparison = {"schema": "g31.version_bound_mechanism_comparison.v1",
              "baseline": str(old.relative_to(root)), "candidate": str(new.relative_to(root)),
              "receipt_sha256": [sha(old/"receipt.json"), sha(new/"receipt.json")],
              "same_input": load(old/"input.json") == load(new/"input.json"), "policies": {},
              "scope": "Historical native005 full vs native007 compact; exact observed actions/physics, not a single-factor timing attribution"}
for policy in ("reactive", "predictive"):
    with gzip.open(old/f"{policy}_raw.json.gz", "rt", encoding="utf-8") as stream:
        a = json.load(stream)
    with gzip.open(new/f"{policy}_raw.json.gz", "rt", encoding="utf-8") as stream:
        b = json.load(stream)
    checks = {key: a["result"][key] == b["result"][key] for key in ("jobs", "trays", "receipts", "transfers")}
    checks["all_submitted_requests_and_replies"] = a["submitted"] == b["submitted"]
    checks["reached_common_horizon"] = a["status"] == b["status"] == "reached" and a["result"]["horizon"] == b["result"]["horizon"] == 86400
    checks["all_control_intents"] = [r["decision"]["intents"] for r in a["control_records"]] == [r["decision"]["intents"] for r in b["control_records"]]
    # Old list publication caches migrate using the exact same signature ABI.
    state = a["controller_state"]
    for owner, value in list(state["published"].items()):
        if isinstance(value, list):
            state["published"][owner] = demand_signature(value)
    checks["controller_state_after_signature_migration"] = state == b["controller_state"]
    comparison["policies"][policy] = checks
comparison["status"] = "equivalent" if comparison["same_input"] and all(all(c.values()) for c in comparison["policies"].values()) else "mismatch"
destination = base / "p2_original_mechanism_24_compact_comparison_007_001.json"
if destination.exists():
    raise FileExistsError(destination)
destination.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

paths = ["p1_build_007/receipt.json", "compact_control_native_001/receipt.json",
         "compact_control_tests_001/first_run_note.json", "compact_control_tests_002/receipt.json",
         "p2_original_1x_reactive_full_H86400_007_001/receipt.json",
         "p2_original_1x_reactive_compact_H86400_007_001/receipt.json",
         "p2_original_2x_reactive_full_H86400_007_001/receipt.json",
         "p2_original_2x_reactive_compact_H86400_007_001/receipt.json",
         "p2_original_1x_reactive_representation_comparison_007_001.json",
         "p2_original_2x_reactive_representation_comparison_007_001.json",
         "p2_original_mechanism_24_compact_007_001/receipt.json", destination.name]
index = root/"docs/g31_ics_circulation/RESULT_INDEX.jsonl"
existing = {json.loads(line)["id"] for line in index.read_text(encoding="utf-8").splitlines()}
entries = []
for name in paths:
    path = base/name
    data = load(path)
    key = "LT-RAW-" + name
    if key in existing:
        raise ValueError("already indexed: " + key)
    entries.append({"id": key, "artifacts": str(path.relative_to(root)), "artifact_sha256": sha(path),
                    "recorded_status": data.get("status", "see_raw_note"), "source_changed": data.get("source_changed"),
                    "binary_sha256": data.get("binary_sha256"), "independent_source": False,
                    "scope": "Exact observation representation / version-bound physical compatibility; not complete 100ms or novel solver certification"})
with index.open("a", encoding="utf-8") as stream:
    for entry in entries:
        stream.write(json.dumps(entry, ensure_ascii=False)+"\n")
print(json.dumps({"comparison_status": comparison["status"], "checks": comparison["policies"], "indexed": len(entries)}, indent=2))
