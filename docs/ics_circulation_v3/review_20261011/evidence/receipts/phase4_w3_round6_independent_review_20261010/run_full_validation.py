"""One frozen complete ICS regression; source and test hashes bind the run."""
from pathlib import Path
import contextlib
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / "full_validation"
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import pytest
    started, cpu = time.perf_counter(), time.process_time()
    OUT.mkdir(exist_ok=False)
    sources = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py"))
    tests = sorted((ROOT / "tests").glob("test_ics_circulation_v3*.py"))
    cpp = ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp"
    paths = sources + tests + [cpp]
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    assert before[cpp.relative_to(ROOT).as_posix()] == "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"
    (OUT / "before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    snapshot = OUT / "source_snapshot"
    for path in paths:
        target = snapshot / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    arguments = [str(p) for p in tests] + ["-q", "--basetemp=.tmp/pytest_round6_full_validation_20261010",
        "--junitxml=" + str(OUT / "junit.xml"), "--durations=10"]
    (OUT / "protocol.json").write_text(json.dumps({"source_file_count": len(sources),
        "test_file_count": len(tests), "arguments": arguments,
        "scope": "all existing test_ics_circulation_v3*.py; no prior failures deleted",
        "source_snapshot_sha256": before}, indent=2) + "\n", encoding="utf-8")
    test_started, test_cpu = time.perf_counter(), time.process_time()
    with (OUT / "pytest.txt").open("w", encoding="utf-8") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        exit_code = int(pytest.main(arguments))
    after = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    suites = ET.parse(OUT / "junit.xml").getroot().findall("testsuite")
    counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    result = {"schema": "ics_v3_round6_complete_regression_v1", "exit_code": exit_code,
        **counts, "test_wall_seconds": time.perf_counter() - test_started,
        "test_cpu_seconds": time.process_time() - test_cpu,
        "wall_seconds": time.perf_counter() - started, "cpu_seconds": time.process_time() - cpu,
        "source_file_count": len(sources), "test_file_count": len(tests),
        "source_and_test_and_cpp_unchanged": before == after,
        "changed_files": [p for p in before if before[p] != after[p]],
        "before": before, "after": after,
        "resource_scope": "one process pytest invocation; total cpu includes snapshots and binding, test CPU is nested"}
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    manifest = {p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"before", "after"}}))
    return exit_code if exit_code else int(before != after)


if __name__ == "__main__":
    raise SystemExit(main())
