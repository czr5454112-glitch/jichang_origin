"""Run native/Python circulation regressions with explicit binary provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).absolute().parents[3]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot() -> dict[str, str]:
    paths = [ROOT / "CMakeLists.txt", *ROOT.glob("cpp/**/*.hpp"), *ROOT.glob("cpp/**/*.cpp"),
             *ROOT.glob("scripts/experiments/g31_ics_circulation/*.py"),
             *ROOT.glob("tests/test_g31_circulation_*.py"),
             ROOT / "tests/test_g31_fixed_blocking_certificate.py",
             ROOT / "tests/test_g31_original_mechanism.py"]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--historical-order-binary", type=Path,
        default=ROOT / "build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd",
        help="Frozen011 artifact for the retained epsilon-order historical counterexample; never substitutes for the current native")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-chain-evidence", type=Path,
        default=ROOT / "outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003",
        help="Explicit frozen native evidence for one read-only synthetic reuse-chain reassessment test")
    parser.add_argument("--timing-reference-evidence", type=Path,
        default=ROOT / "outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_003",
        help="Explicit frozen96-branch timing evidence, including all35 unknown action outcomes")
    parser.add_argument("--reuse-v2-evidence", type=Path,
        default=ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014/reuse_v2_002",
        help="Explicit frozen117-branch v2.1 evidence; all branches are reassessed without a missing-artifact skip")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    binary = args.binary.absolute()
    build = json.loads(args.build_receipt.read_text(encoding="utf-8"))
    before = snapshot()
    binary_hash = sha(binary)
    historical = args.historical_order_binary.absolute()
    historical_expected = "19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec"
    compiled_mismatch = [p for p, digest in build["source_after"].items() if before.get(p) != digest]
    tests = sorted({str(p.relative_to(ROOT)) for p in ROOT.glob("tests/test_g31_circulation_*.py")} |
                   {"tests/test_g31_fixed_blocking_certificate.py",
                    "tests/test_g31_original_mechanism.py"})
    command = [sys.executable, "-m", "pytest", "-q", *tests,
               "--junitxml=" + str((args.output / "junit.xml").absolute()),
               # This newly created campaign owns its temporary directory.
               # Do not depend on a shared Windows Temp pytest root whose
               # permissions may belong to a different execution context.
               "--basetemp=" + str((args.output / "pytest_tmp").absolute())]
    receipt = {"schema": "g31.live_regression.v1", "status": "running", "command": command,
               "binary": str(binary), "binary_sha256": binary_hash,
               "build_receipt": str(args.build_receipt), "build_receipt_sha256": sha(args.build_receipt),
               "compiled_source_mismatch": compiled_mismatch, "source_before": before,
               "test_files": tests, "environment": {"G31_CIRCULATION_BINARY": str(binary),
                    "G31_HISTORICAL_ORDER_BINARY": str(historical),
                    "G31_REUSE_CHAIN_EVIDENCE": str(args.reuse_chain_evidence.absolute()),
                    "G31_TIMING_REFERENCE_EVIDENCE": str(args.timing_reference_evidence.absolute()),
                    "G31_REUSE_V2_EVIDENCE": str(args.reuse_v2_evidence.absolute()),
                    "PYTHONPATH": "src;.", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}}
    receipt["historical_order_regression"] = {
        "binary": str(historical), "expected_sha256": historical_expected,
        "scope": "One retained historical epsilon-order counterexample runs frozen011. The separately listed native identity checks also exercise pinned historical binaries in isolated child processes. Current strict-order protection has a separate regression using the supplied current artifact. No skip or fallback.",
        "current_model_claim": False}
    start = time.perf_counter()
    try:
        evidence_files = [args.reuse_chain_evidence / "receipt.json",
                          *sorted(args.reuse_chain_evidence.glob("gate*/input.json")),
                          *sorted(args.reuse_chain_evidence.glob("gate*/route*.json.gz"))]
        if len(evidence_files) != 28:
            raise RuntimeError("reuse-chain saved evidence requires receipt, three inputs and all24 native cells")
        evidence_hashes = {str(p.absolute()): sha(p) for p in evidence_files}
        receipt["saved_native_evidence_reassessment"] = {
            "source_before": evidence_hashes,
            "scope": "One read-only test re-assesses frozen24 synthetic native branches; does not launch new native branches or certify original flow."}
        timing_files = [args.timing_reference_evidence / name for name in
                        ("receipt.json", "preregistered_protocol.json", "branch_ledger.json")]
        timing_files += sorted(args.timing_reference_evidence.glob("gate*/input.json"))
        timing_files += sorted(args.timing_reference_evidence.glob("gate*/*.json.gz"))
        if len(timing_files) != 102:
            raise RuntimeError("timing evidence requires receipt, protocol, ledger, three inputs and all96 raw branches")
        timing_hashes = {str(p.absolute()): sha(p) for p in timing_files}
        receipt["saved_timing_reference_reassessment"] = {"source_before": timing_hashes,
            "scope": "One read-only test re-assesses all96 frozen branches, retaining35 unknowns. Not96 new native executions or a complete stronger reference."}
        v2_files = [args.reuse_v2_evidence / name for name in
                    ("receipt.json", "preregistered_protocol.json", "branch_ledger.json")]
        v2_files += sorted(args.reuse_v2_evidence.glob("gate*/input.json"))
        v2_files += sorted(args.reuse_v2_evidence.glob("gate*/*.json.gz"))
        if len(v2_files) != 123:
            raise RuntimeError("reuse v2 evidence requires receipt, protocol, ledger, three inputs and all117 raw branches")
        v2_hashes = {str(p.absolute()): sha(p) for p in v2_files}
        receipt["saved_reuse_v2_reassessment"] = {"source_before": v2_hashes,
            "scope": "One read-only test re-assesses all117 frozen v2.1 branches and negative later-feedback contrasts; not new native executions or original-flow validation."}
        if build["status"] != "passed" or build["source_changed"] or compiled_mismatch:
            raise RuntimeError("source does not match a successful clean build")
        if binary_hash not in build["binary_sha256"].values():
            raise RuntimeError("binary hash is absent from clean build receipt")
        historical_hash = sha(historical)
        receipt["historical_order_regression"]["actual_sha256"] = historical_hash
        if historical_hash != historical_expected:
            raise RuntimeError("historical epsilon-order witness requires the exact frozen011 binary")
        env = dict(os.environ, **receipt["environment"], PYTHONIOENCODING="utf-8")
        with (args.output / "stdout.log").open("wb") as out, (args.output / "stderr.log").open("wb") as err:
            run = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=err,
                                 timeout=args.timeout, check=False)
        receipt["exit_code"] = run.returncode
        cases = ET.parse(args.output / "junit.xml").findall(".//testcase")
        receipt["counts"] = {"tests": len(cases),
                             "failures": sum(c.find("failure") is not None for c in cases),
                             "errors": sum(c.find("error") is not None for c in cases),
                             "skipped": sum(c.find("skipped") is not None for c in cases)}
        historical_cases = [c for c in cases if c.get("name", "").startswith("test_historical_epsilon_order_scope")]
        receipt["historical_order_regression"]["test_names"] = [c.get("name") for c in historical_cases]
        receipt["historical_order_regression"]["test_count"] = len(historical_cases)
        identity_cases = [c for c in cases if c.get("classname", "").endswith("test_g31_circulation_native_identity")]
        receipt["native_identity_regression"] = {
            "test_names": [c.get("name") for c in identity_cases],
            "test_count": len(identity_cases),
            "scope": "Pinned native011/native015 identity and distinct historical behavior checked in isolated child processes; not current-model physical validation.",
            "current_model_claim": False}
        receipt["current_native_and_python_test_count"] = len(cases) - len(historical_cases) - len(identity_cases)
        receipt["counts_scope"] = "Aggregate includes the explicitly listed historical011 witness; current native, Python and identity checks are separately identified by JUnit names. Not all tests certify the current physical model."
        saved_cases = [c for c in cases if c.get("name") == "test_saved_native_all_cells_reassess_and_keep_negative_regimes"]
        receipt["saved_native_evidence_reassessment"]["test_count"] = len(saved_cases)
        if len(saved_cases) != 1 or any(sha(Path(p)) != h for p, h in evidence_hashes.items()):
            raise RuntimeError("saved native evidence was not tested exactly once or changed during verification")
        timing_cases = [c for c in cases if c.get("name") == "test_saved_all96_branches_match_frozen_plan_and_reassessment"]
        receipt["saved_timing_reference_reassessment"]["test_count"] = len(timing_cases)
        if len(timing_cases) != 1 or any(sha(Path(p)) != h for p, h in timing_hashes.items()):
            raise RuntimeError("saved timing evidence was not tested exactly once or changed during verification")
        v2_cases = [c for c in cases if c.get("name") == "test_saved117_native_cells_reassess_and_retain_negative_causal_result"]
        receipt["saved_reuse_v2_reassessment"]["test_count"] = len(v2_cases)
        if len(v2_cases) != 1 or any(sha(Path(p)) != h for p, h in v2_hashes.items()):
            raise RuntimeError("saved reuse v2 evidence was not tested exactly once or changed during verification")
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = sorted(k for k in before.keys() | receipt["source_after"].keys()
                                           if before.get(k) != receipt["source_after"].get(k))
        if run.returncode or not cases or any(receipt["counts"][k] for k in ("failures", "errors", "skipped")):
            raise RuntimeError("regression did not complete without failure/error/skip")
        if len(historical_cases) != 1:
            raise RuntimeError("retained historical epsilon-order counterexample was not run exactly once")
        if receipt["source_changed"] or sha(binary) != binary_hash:
            raise RuntimeError("source or binary changed during verification")
        receipt["status"] = "passed"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = repr(exc)
    finally:
        receipt["wall_seconds"] = time.perf_counter() - start
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "counts", "error") if k in receipt}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
