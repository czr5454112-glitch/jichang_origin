"""Reproduce the complete local ICS test manifest without changing sources."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, process_time
import traceback
import xml.etree.ElementTree as ET

import pytest


OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[3]
CPP = ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp"
EXPECTED_CPP = "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def code_manifest():
    files = sorted((ROOT / "scripts/experiments/ics_circulation_v3").rglob("*.py"))
    files += sorted((ROOT / "tests").glob("test_ics_circulation_v3*.py"))
    return {relative(path): file_sha(path) for path in files}


def save(name, value):
    with (OUTPUT / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    if {p.name for p in OUTPUT.iterdir()} != {"run_validation.py"}:
        raise ValueError("Validation output is not fresh; previous records cannot be overwritten")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    test_files = sorted((ROOT / "tests").glob("test_ics_circulation_v3*.py"))
    names = [relative(path) for path in test_files]
    required = {"tests/test_ics_circulation_v3_distributed_local.py",
                "tests/test_ics_circulation_v3_paired_development.py"}
    if not required <= set(names):
        raise ValueError("New local and paired development tests must be included")
    before = code_manifest()
    cpp_before = file_sha(CPP)
    save("source_hashes_before.json", before)
    save("test_file_manifest.json", {"selection": "tests/test_ics_circulation_v3*.py",
        "file_count": len(names), "files": [{"path": name, "sha256": before[name]} for name in names],
        "required_new_tests_present": sorted(required)})
    args = [*names, "-q", "--color=no", "--basetemp", str(ROOT / ".tmp/ics_v3_local_validation_20261009"),
            "--junitxml", str(OUTPUT / "pytest.xml")]
    start_utc = datetime.now(timezone.utc).isoformat()
    wall, cpu = perf_counter(), process_time()
    exception = None
    with (OUTPUT / "pytest.log").open("x", encoding="utf-8", newline="\n") as log:
        with redirect_stdout(log), redirect_stderr(log):
            try:
                return_code = int(pytest.main(args))
            except BaseException as exc:
                return_code = 99
                exception = {"type": type(exc).__name__, "message": str(exc)}
                traceback.print_exc()
    elapsed, cpu_elapsed = perf_counter() - wall, process_time() - cpu
    after = code_manifest()
    cpp_after = file_sha(CPP)
    save("source_hashes_after.json", after)
    changes = [{"path": name, "before": before.get(name), "after": after.get(name)}
               for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
    counts, failures = {}, []
    if (OUTPUT / "pytest.xml").is_file():
        document = ET.parse(OUTPUT / "pytest.xml")
        cases = list(document.iter("testcase"))
        counts = {"testcases": len(cases), "failed": sum(c.find("failure") is not None for c in cases),
                  "errors": sum(c.find("error") is not None for c in cases),
                  "skipped": sum(c.find("skipped") is not None for c in cases)}
        counts["passed"] = counts["testcases"] - counts["failed"] - counts["errors"] - counts["skipped"]
        for case in cases:
            for kind in ("failure", "error"):
                issue = case.find(kind)
                if issue is not None:
                    failures.append({"class": case.get("classname"), "name": case.get("name"),
                                     "type": kind, "message": issue.get("message"), "detail": (issue.text or "")[:4000]})
    manifest = {"schema": "ics_v3_phase4_local_validation_v1", "started_at_utc": start_utc,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(), "cwd": str(ROOT),
        "python_executable": sys.executable, "python_version": sys.version, "platform": platform.platform(),
        "pytest_version": pytest.__version__, "invocation": "pytest.main in this recorded Python process",
        "pytest_arguments": args, "test_file_count": len(names), "source_and_test_file_count": len(before),
        "source_py_count": sum(name.startswith("scripts/") for name in before),
        "return_code": return_code, "counts": counts, "failures": failures, "exception": exception,
        "wall_seconds": elapsed, "process_cpu_seconds": cpu_elapsed,
        "cpu_scope": "pytest host process including its threads; child subprocess CPU is not included",
        "source_changes_during_run": changes, "all_source_hashes_unchanged": not changes,
        "cpp": {"path": relative(CPP), "expected_sha256": EXPECTED_CPP, "before_sha256": cpp_before,
                "after_sha256": cpp_after, "unchanged": cpp_before == cpp_after,
                "matches_preexisting_hash": cpp_before == cpp_after == EXPECTED_CPP},
        "runner_sha256": file_sha(Path(__file__)),
        "artifact_sha256": {name: file_sha(OUTPUT / name) for name in
            ("test_file_manifest.json", "source_hashes_before.json", "source_hashes_after.json", "pytest.log", "pytest.xml")
            if (OUTPUT / name).is_file()}}
    save("validation_manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("test_file_count", "source_py_count", "return_code", "counts",
                                                    "wall_seconds", "process_cpu_seconds", "all_source_hashes_unchanged")}))
    return int(bool(return_code or changes or cpp_before != cpp_after or cpp_after != EXPECTED_CPP))


if __name__ == "__main__":
    raise SystemExit(main())
