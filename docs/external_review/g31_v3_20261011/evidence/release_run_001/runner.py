"""Run the complete frozen ICS test set from an exported review checkout.

Prepare the lossless fixtures first. Results belong to a new output directory;
this is publication verification, separate from the Round11 experiment ledger.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, process_time
import traceback
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cpu, wall = process_time(), perf_counter()
    manifest_path = root / "docs/ics_circulation_v3/review_20261011/source_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    sources = manifest["python_source_and_tests"]
    tests = [p for p in sources if p.startswith("tests/")]
    report = dict(status="failed", test_files=len(tests), expected_tests=1519,
        python=sys.version, platform=platform.platform(),
        source_manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(),
        exact_total_physical_runs=None, exact_total_cpu_seconds=None,
        resource_scope="Same-process interval after argument/output preparation; pytest is nested; any subprocess CPU and uninstrumented test physics remain unknown; final writes excluded.")
    def hashes():
        return {p: sha256((root / p).read_bytes()).hexdigest() for p in sources}
    before = None
    try:
        before = hashes()
        assert len(tests) == 89 and len(sources) == 211
        assert all(before[p] == sources[p]["working_bytes_sha256"] for p in sources), "exported source differs from frozen published bytes"
        os.chdir(root)
        sys.path.insert(0, str(root))
        import pytest
        report["pytest_version"] = pytest.__version__
        result = pytest.main(["-q", *tests, "--basetemp", str(output / "pytest_tmp"),
                              "--junitxml", str(output / "junit.xml")])
        report["pytest_exit_code"] = int(result)
        suites = ET.parse(output / "junit.xml").getroot()
        cases = list(suites.iter("testcase"))
        failures = sum(case.find("failure") is not None for case in cases)
        errors = sum(case.find("error") is not None for case in cases)
        skipped = sum(case.find("skipped") is not None for case in cases)
        report["outcomes"] = dict(total=len(cases), passed=len(cases)-failures-errors-skipped,
                                  failed=failures, errors=errors, skipped=skipped)
        assert int(result) == 0 and report["outcomes"] == dict(total=1519, passed=1519, failed=0, errors=0, skipped=0)
        report["status"] = "passed"
    except Exception:
        report["exception"] = traceback.format_exc()
    finally:
        try:
            after = hashes()
            report["source_changed"] = [p for p in before or {} if before[p] != after[p]]
            if report["source_changed"]:
                report["status"] = "failed"
            (output / "source_after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
        except Exception:
            report["status"] = "failed"
            report["source_after_error"] = traceback.format_exc()
        if before is not None:
            (output / "source_before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
        report.update(cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
                      runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
        (output / "runner.py").write_bytes(Path(__file__).read_bytes())
        (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
