"""Recount existing raw evidence and preserve build logs; does not rerun tests."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).absolute().parents[3]
OUT = Path(__file__).absolute().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recount(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    counts = {"tests": len(cases), "failed": sum(c.find("failure") is not None for c in cases),
              "errors": sum(c.find("error") is not None for c in cases),
              "skipped": sum(c.find("skipped") is not None for c in cases)}
    counts["passed"] = counts["tests"] - sum(counts[k] for k in ("failed", "errors", "skipped"))
    return counts


def mismatches(mapping):
    return [p for p, expected in mapping.items() if sha(ROOT / p) != expected]


def main():
    build = read(OUT / "build_final_002/receipt.json")
    native = read(OUT / "native_acceptance_final/receipt.json")
    v3 = read(OUT / "v3_correctness/full_001/results.json")
    v3_before = read(OUT / "v3_correctness/before_probes.json")
    v3_after = read(OUT / "v3_correctness/after_probes.json")
    ctest = read(ROOT / "build_g31_current/final_all_002_receipt.json")
    ctest_sources = read(ROOT / "build_g31_current/final_all_002_source_after.json")
    ctest_binaries = read(ROOT / "build_g31_current/final_all_002_binary_sha256.json")
    parity = read(ROOT / "build_g31_parity/final_receipt.json")
    pinned = read(ROOT / "build_g31_parity/pinned_result.json")
    current = read(ROOT / "build_g31_parity/current_result.json")
    evidence = {
        "schema": "g31.circulation.final_verification.v1",
        "scope": "Independent recount/hash comparison of existing executions, not another test execution",
        "v3_junit": recount(OUT / "v3_correctness/full_001/junit.xml"),
        "native_python_junit": recount(OUT / "native_pytest_final.xml"),
        "native_ctest_junit": recount(ROOT / "build_g31_current/final_all_002_junit.xml"),
        "v3_defects_before": v3_before["observed_defect_keys"],
        "v3_defects_after": v3_after["observed_defect_keys"],
        "v3_original_tests_byte_unchanged": v3["original_test_bytes_unchanged"],
        "v3_current_source_mismatches": mismatches(read(OUT / "v3_correctness/full_001/source_after.json")),
        "native_build_current_source_mismatches": mismatches(build["source_after"]),
        "native_case_current_source_mismatches": mismatches(native["source_sha256"]),
        "native_ctest_current_source_mismatches": mismatches({x["path"]: x["sha256"] for x in ctest_sources}),
        "native_build_current_binary_mismatches": mismatches(build["binary_sha256"]),
        "native_ctest_current_binary_mismatches": [x["path"] for x in ctest_binaries
                                                   if sha(ROOT / "build_g31_current" / x["path"]) != x["sha256"]],
        "native_build_and_case_binary_equal": build["binary_sha256"][native["binary"]] == native["binary_sha256"],
        "native_case_acceptance": native["acceptance"],
        "legacy_parity_results_exactly_equal": pinned == current,
        "legacy_parity_scenarios": len(pinned),
        "legacy_parity_hash_comparisons": sum(key.endswith("_sha256") for case in pinned for key in case),
        "legacy_parity_current_binary_matches": sha(ROOT / "build_g31_parity/current.exe") == parity["current_binary_sha256"],
        "legacy_parity_pinned_binary_matches": sha(ROOT / "build_g31_parity/pinned.exe") == parity["pinned_binary_sha256"],
        "legacy_parity_current_runtime_matches": sha(ROOT / "cpp/ics_core/runtime/event_driven_junction.hpp") == parity["current_runtime_sha256"],
        "legacy_parity_fixture_matches": sha(ROOT / "cpp/tests/g31_legacy_replay_fixture.cpp") == parity["fixture_sha256"],
        "protected_original_file_sha256": sha(ROOT.parent / "cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    }
    assert evidence["v3_junit"] == v3["counts"]
    for key, count in (("v3_junit", 1580), ("native_python_junit", 48), ("native_ctest_junit", 16)):
        assert evidence[key] == {"tests": count, "failed": 0, "errors": 0, "skipped": 0, "passed": count}, key
    assert len(evidence["v3_defects_before"]) == 3 and not evidence["v3_defects_after"]
    assert build["status"] == native["status"] == native["acceptance"]["status"] == "passed"
    assert native["acceptance"]["scenario_count"] == 13 and len(native["scenarios"]) == 13
    assert all(s["audit"]["status"] == "passed" for s in native["scenarios"])
    assert build["source_before"] == build["source_after"]
    assert not build["source_changed"] and not native["source_changed"] and not ctest["source_changed"]
    assert not v3["source_changed_during_test"]
    assert all(c["exit_code"] == 0 for c in build["commands"])
    assert ctest["exit_code"] == v3["pytest_exitcode"] == 0
    assert len(build["source_after"]) == 54 and len(ctest_sources) == 53
    assert all(not value for key, value in evidence.items() if key.endswith("mismatches"))
    assert all(value for key, value in evidence.items() if isinstance(value, bool)), "failed evidence check"
    assert evidence["legacy_parity_scenarios"] == 2 and evidence["legacy_parity_hash_comparisons"] == 10
    assert evidence["protected_original_file_sha256"] == "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"
    check = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True)
    assert check.returncode == 0, check.stderr.decode(errors="replace")
    evidence["git_diff_check_exit_code"] = check.returncode
    destination = OUT / "native_legacy_final"
    destination.mkdir(exist_ok=False)
    copies = []
    ctest_files = [p for p in (ROOT / "build_g31_current").iterdir()
                   if p.is_file() and (p.name.startswith("final_all_002") or p.name.startswith("build_final_all"))]
    parity_files = [p for p in (ROOT / "build_g31_parity").iterdir()
                    if p.is_file() and p.suffix in {".json", ".cmd", ".log", ".exitcode"}]
    for folder, files in (("ctest", ctest_files), ("parity", parity_files)):
        (destination / folder).mkdir()
        for source in sorted(files):
            target = destination / folder / source.name
            shutil.copyfile(source, target)
            assert sha(source) == sha(target)
            copies.append({"original": str(source.relative_to(ROOT)), "copy": str(target.relative_to(ROOT)), "sha256": sha(target)})
    (destination / "copy_manifest.json").write_text(json.dumps(copies, indent=2), encoding="utf-8")
    evidence["preserved_build_receipt_files"] = len(copies)
    evidence["status"] = "passed"
    (OUT / "verification_summary.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
