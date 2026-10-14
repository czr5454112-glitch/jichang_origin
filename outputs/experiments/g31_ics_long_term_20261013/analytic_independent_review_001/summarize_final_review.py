"""Read-only cross-check of executed campaign receipts, not a campaign rerun."""
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).absolute().parents[4]
BASE = ROOT / "outputs/experiments/g31_ics_long_term_20261013"
read = lambda path: json.loads(path.read_text(encoding="utf-8"))
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
result = {"schema": "g31.independent.final_evidence_read.v1", "status": "passed",
          "scope": "read and inspect existing full raw results; not independent campaign re-execution", "campaigns": {}}
for dirname, filename in [("analytic_native_010", "finite_reference.json"),
                          ("known_service_native_004", "finite_reference.json"),
                          ("p4_original_first_return_reference_006_001", "finite_reference_raw.json.gz"),
                          ("regional_original_003", "route_reference_raw.json.gz")]:
    directory = BASE / dirname
    if not directory.exists():
        result["campaigns"][dirname] = {"status": "not_yet_available"}
        continue
    receipt = read(directory / "receipt.json")
    target = directory / filename
    if not target.exists():
        result["campaigns"][dirname] = {"status": "raw_reference_not_yet_available", "receipt_status": receipt["status"]}
        continue
    if target.suffix == ".gz":
        with gzip.open(target, "rt", encoding="utf-8") as stream:
            reference = json.load(stream)
    else:
        reference = read(target)
    checks = []
    for row in reference["rows"]:
        if "result" not in row:
            checks.append({"action": row["action"]["action_id"], "status": row["status"]})
            continue
        raw = row["result"]
        comp = row["completion"]
        assert raw["advance"]["horizon_complete"] is True and raw["advance"]["status"] == "reached"
        assert comp["status"] == "reached" and not comp["problems"]
        assert all(value == raw["horizon"] for value in comp["evidence"].values())
        assert row["audit"]["status"] == "passed"
        checks.append({"action": row["action"]["action_id"], "status": row["status"],
                       "horizon": raw["horizon"], "horizon_complete": True,
                       "paired_service_preserved": row.get("paired_service_preserved"),
                       "offered": row["metrics"]["offered"], "completed": row["metrics"]["completed"]})
    assert receipt["source_changed"] == []
    assert reference["global_native_optimality"] == "unknown"
    result["campaigns"][dirname] = {"status": "inspected", "receipt_sha256": digest(directory / "receipt.json"),
        "raw_sha256": digest(target), "binary_sha256": receipt["binary_sha256"],
        "optimality": reference["optimality"], "exhaustive": reference["exhaustive"],
        "global_native_optimality": reference["global_native_optimality"],
        "distinct_verified_physical_outcomes": reference["distinct_verified_physical_outcomes"],
        "checks": checks}
    if dirname == "regional_original_003":
        actual_input, selection = read(directory / "input.json"), read(directory / "selection.json")
        input_hash = hashlib.sha256(json.dumps(actual_input, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        assert input_hash == selection["input_sha256"]
        assert input_hash != selection["base_selected_input_sha256"]
        result["campaigns"][dirname]["final_input_sha256_verified"] = input_hash
xml = ET.parse(BASE / "analytic_independent_review_001/final_006_junit.xml").getroot()
suite = xml.find("testsuite")
result["independently_rerun_junit"] = dict(suite.attrib)
assert suite.attrib["tests"] == "65" and all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
own = read(BASE / "analytic_completion_independent_after_003/receipt.json")
assert own["status"] == "passed" and len(own["cases"]) == 29 and own["source_changed"] == []
result["independent_completion_checks"] = {"case_count": len(own["cases"]), "status": own["status"],
    "source_sha256": own["source_after"], "binary_sha256": own["binary_sha256"]}
Path(__file__).with_name("final_evidence_checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({"status": result["status"], "campaigns": {k:v["status"] for k,v in result["campaigns"].items()},
                  "independent_tests": suite.attrib["tests"], "independent_metadata_cases": 29}))
