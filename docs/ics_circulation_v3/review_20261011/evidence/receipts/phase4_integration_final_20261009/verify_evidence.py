"""Read Phase 4 evidence without importing or executing experiment code.

Run from any directory with Python's standard library. An existing report is
never replaced; use --output NEW_PATH for a later verification. This verifies
recorded evidence integrity, not scientific claims or source-at-test-time.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
CODE = ROOT / "scripts/experiments/ics_circulation_v3"
HERE = Path(__file__).resolve().parent
FINAL_GROUPS = {
    "phase4_routing_repair_20261009",
    "phase4_request_semantics_release_20261009",
    "phase4_coupling_final_20261009",
}
CPP = ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp"
CPP_EXPECTED = "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def verify() -> dict:
    started = time.perf_counter()
    issues = []
    inputs = {}

    def issue(where, detail):
        issues.append({"where": where, "detail": detail})

    def read_json(path):
        inputs[relative(path)] = sha(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def guarded(name, action):
        try:
            return action()
        except Exception as exc:
            issue(name, f"{type(exc).__name__}: {exc}")
            return {"passed": False, "read_error": f"{type(exc).__name__}: {exc}"}

    def snapshots():
        results = []
        for directory in sorted(BASE.glob("phase4*")):
            snapshot = directory / "source_snapshot"
            if not snapshot.is_dir():
                continue
            required_current = directory.name in FINAL_GROUPS
            manifests = {}
            flags = {}
            for filename in ("summary.json", "protocol.json"):
                path = directory / filename
                if path.is_file():
                    payload = read_json(path)
                    mapping = payload.get("source_sha256")
                    if isinstance(mapping, dict) and mapping:
                        manifests[filename] = mapping
                    else:
                        issue(relative(path), "Missing nonempty source_sha256 mapping")
                    for key in ("source_changed_during_run", "source_unchanged_after"):
                        if key in payload:
                            flags[key] = payload[key]
            if not manifests:
                issue(relative(directory), "Existing source_snapshot has no hash manifest")
            names = sorted(set().union(*(set(m) for m in manifests.values())))
            actual_names = {p.relative_to(snapshot).as_posix()
                            for p in snapshot.rglob("*") if p.is_file()}
            for unexpected in sorted(actual_names - set(names)):
                issue(relative(snapshot / unexpected), "Snapshot file absent from recorded manifests")
            rows = []
            for name in names:
                if Path(name).name != name or not name.endswith(".py"):
                    issue(relative(directory), f"Unsupported or unsafe manifest key: {name!r}")
                    continue
                expected = {filename: mapping[name] for filename, mapping in manifests.items()
                            if name in mapping}
                expected_valid = all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)
                                     for h in expected.values())
                snapshot_hash = sha(snapshot / name) if (snapshot / name).is_file() else None
                current_hash = sha(CODE / name) if required_current and (CODE / name).is_file() else None
                match = bool(expected_valid and snapshot_hash and
                             all(h == snapshot_hash for h in expected.values()))
                current_match = bool(match and current_hash == snapshot_hash) if required_current else None
                row = {"file": name, "expected_sha256": expected,
                       "snapshot_sha256": snapshot_hash, "snapshot_matches": match}
                if required_current:
                    row.update(current_sha256=current_hash, current_matches=current_match)
                rows.append(row)
                if not match or (required_current and not current_match):
                    issue(relative(snapshot / name), "Recorded manifest/snapshot/current mismatch"
                          if required_current else "Recorded manifest/snapshot mismatch")
            if flags.get("source_changed_during_run", False) is not False:
                issue(relative(directory), "Recorded source_changed_during_run is not false")
            if flags.get("source_unchanged_after", True) is not True:
                issue(relative(directory), "Recorded source_unchanged_after is not true")
            results.append({"directory": relative(directory), "require_current_match": required_current,
                            "recorded_flags": flags, "manifest_files": sorted(manifests),
                            "snapshot_file_count": len(actual_names), "files": rows,
                            "passed": bool(manifests) and len(rows) == len(actual_names) and
                            all(r["snapshot_matches"] and r.get("current_matches", True) for r in rows)})
        present = {Path(r["directory"]).name for r in results}
        for missing in sorted(FINAL_GROUPS - present):
            issue(missing, "Final required source_snapshot directory missing")
        return results

    def external():
        directory = ROOT / "docs/ics_circulation_v3/phase4_external_review_20261009"
        manifest = read_json(directory / "authoring_validation.json")
        entries = manifest["artifact_files"]
        rows = []
        if len(entries) != 4:
            issue("external_inputs", "Expected exactly four authoring artifact entries")
        for entry in entries:
            name = entry["file"]
            if Path(name).name != name:
                raise ValueError(f"Unsafe external artifact name {name!r}")
            path = directory / name
            actual = sha(path)
            size = path.stat().st_size
            passed = actual == entry["sha256"] and size == entry["size_bytes"]
            rows.append({"file": relative(path), "expected_sha256": entry["sha256"],
                         "actual_sha256": actual, "expected_bytes": entry["size_bytes"],
                         "actual_bytes": size, "passed": passed})
            if not passed:
                issue(relative(path), "External authoring hash/size mismatch")
        return {"passed": len(entries) == 4 and all(r["passed"] for r in rows), "files": rows}

    def probes():
        path = BASE / "phase4_review_probes_frozen_20261009.json"
        data = read_json(path)
        sources = data["source_hashes"]
        source_rows = [{"file": name, **entry} for name, entry in sorted(sources.items())]
        source_ok = bool(source_rows) and all(r["matches"] is True and
                     r["sha256"] == r["expected_sha256"] for r in source_rows)
        rows = [{"probe": name, "diagnostic_exposed": value["diagnostic_exposed"],
                 "execution": value["execution"]} for name, value in sorted(data["probes"].items())]
        passed = (data["source_matches_frozen_manifest"] is True and source_ok and
                  len(rows) == 5 and all(r["diagnostic_exposed"] is True for r in rows) and
                  data["execution_error_count"] == 0)
        if not passed:
            issue(relative(path), "Frozen source-match/exposed-probe requirements failed")
        return {"passed": passed, "prepared_for_commit": data["prepared_for_commit"],
                "source_matches_frozen_manifest": data["source_matches_frozen_manifest"],
                "source_hashes": source_rows, "probes": rows,
                "execution_error_count": data["execution_error_count"],
                "qualification": "Verifies the recorded frozen-probe evidence, not a rerun or current-code probe result."}

    def tests():
        path = HERE / "tests.xml"
        inputs[relative(path)] = sha(path)
        xml = ET.parse(path).getroot()
        suites = list(xml.iter("testsuite"))
        cases = list(xml.iter("testcase"))
        declared = {name: sum(int(s.get(name, "0")) for s in suites)
                    for name in ("tests", "failures", "errors", "skipped")}
        actual = {name: sum(c.find(name) is not None for c in cases)
                  for name in ("failure", "error", "skipped")}
        counts = Counter(c.get("classname", "") for c in cases)
        log_path = HERE / "pytest.log"
        inputs[relative(log_path)] = sha(log_path)
        line = re.search(r"(\d+) passed in ([\d.]+)s", log_path.read_text(encoding="utf-8"))
        passed = (len(suites) == 1 and declared == {"tests": 344, "failures": 0, "errors": 0, "skipped": 0}
                  and len(cases) == 344 and not any(actual.values()) and
                  line is not None and int(line.group(1)) == 344)
        if not passed:
            issue(relative(path), "XML/log do not establish exactly 344 passing cases without skips/errors/failures")
        return {"passed": passed, "declared": declared, "actual_testcase_count": len(cases),
                "actual_nonpasses": actual, "per_test_module": dict(sorted(counts.items())),
                "xml_elapsed_seconds": [float(s.get("time", "0")) for s in suites],
                "log_elapsed_seconds": float(line.group(2)) if line else None,
                "rerun_performed": False}

    def cpp():
        actual = sha(CPP)
        passed = actual == CPP_EXPECTED
        if not passed:
            issue(relative(CPP), "C++ hash differs from the preexisting hash supplied by the coordinator")
        return {"file": relative(CPP), "expected_sha256": CPP_EXPECTED,
                "actual_sha256": actual, "passed": passed}

    def contracts():
        directory = BASE / "phase4_coupling_final_20261009"
        rows = []
        for path in sorted(directory.glob("*__predictive_*.json")):
            contract = read_json(path)["control_contract"]
            unhashed = {k: v for k, v in contract.items() if k != "contract_sha256"}
            checksum_ok = (canonical_sha(unhashed) == contract["contract_sha256"] and
                           canonical_sha(contract["information"]) == contract["information_sha256"] and
                           canonical_sha(contract["continuation"]) == contract["continuation_sha256"])
            dependencies = contract["continuation"]["implementation_sha256"]
            bad = []
            for name, expected in dependencies.items():
                if Path(name).name != name:
                    raise ValueError(f"Unsafe contract dependency {name!r}")
                if not (expected == sha(CODE / name) == sha(directory / "source_snapshot" / name)):
                    bad.append(name)
            passed = bool(dependencies) and checksum_ok and not bad
            rows.append({"file": path.name, "contract_sha256": contract["contract_sha256"],
                         "dependency_count": len(dependencies), "checksums_match": checksum_ok,
                         "dependency_mismatches": bad, "passed": passed})
            if not passed:
                issue(relative(path), "Control contract checksum/dependency mismatch")
        if len(rows) != 18:
            issue(relative(directory), "Expected exactly 18 recorded coupling control contracts")
        return {"passed": len(rows) == 18 and all(r["passed"] for r in rows), "files": rows}

    source_paths = sorted(CODE.rglob("*.py"))
    test_paths = sorted((ROOT / "tests").glob("test_ics_circulation_v3_*.py"))
    inventory = [{"file": relative(p), "sha256": sha(p), "kind": kind}
                 for kind, paths in (("experiment_source", source_paths), ("test", test_paths)) for p in paths]
    results = {
        "schema": "ics_v3_phase4_evidence_verification_v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verifier_sha256": sha(Path(__file__)),
        "scope": "Read-only integrity checks; no test, probe, simulator, or performance experiment rerun.",
        "source_snapshots": guarded("source_snapshots", snapshots),
        "external_inputs": guarded("external_inputs", external),
        "frozen_probes": guarded("frozen_probes", probes),
        "integration_tests": guarded("integration_tests", tests),
        "preserved_cpp": guarded("preserved_cpp", cpp),
        "final_coupling_control_contracts": guarded("final_coupling_control_contracts", contracts),
        "current_test_source_inventory": {"source_count": len(source_paths), "test_file_count": len(test_paths),
            "files": inventory, "inventory_sha256": canonical_sha(inventory),
            "qualification": "Hashes recorded after the test run. XML alone does not cryptographically prove source-at-test-time; no test rerun was requested."},
        "limitations": [
            "Historical snapshots are compared to their own recorded manifests; only the three designated final groups must match current source.",
            "Directories without source_snapshot are not retroactively required to have snapshots; unmanifested direct diagnostic source copies are outside this snapshot check.",
            "Recorded dependency lists are honored; this does not establish that each historical manifest captured a complete transitive dependency closure.",
        ],
    }
    changed = [r["file"] for r in inventory if sha(ROOT / r["file"]) != r["sha256"]]
    for path in changed:
        issue(path, "Current source changed during verification")
    results["source_changed_during_verification"] = changed
    results["input_manifest_sha256"] = dict(sorted(inputs.items()))
    results["discrepancies"] = issues
    results["passed"] = not issues
    results["verification_elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "evidence_verification.json")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; choose a new output file to preserve prior evidence")
    if not args.output.parent.is_dir():
        parser.error("Output parent directory must already exist")
    result = verify()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "discrepancies": result["discrepancies"],
                      "output": str(args.output), "seconds": result["verification_elapsed_seconds"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
