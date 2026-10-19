"""Native022 phase capture beside the unchanged conservative request ledger.

Original complete input/config and all offered/update denominators are retained.
No native time is subtracted. Use only after the parent releases a native slot.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import time

from . import profile_request_bundles as driver
from . import request_bundle_measurement as bundles
from .capture_native_request_timing import CaptureNamespaces, capture_session
from .native_request_timing import analyze_native_timing


class _RecentBundleProxy(bundles._PolicySessionProxy):
    def observe_protocol_control_policy_recent(self, owner, validity):
        return self._recorder.invoke("observe_protocol_control_policy_recent",
            self._recorder.session.observe_protocol_control_policy_recent, owner, validity)


class NativePhaseBundleRecorder(bundles.BundleRecorder):
    capacity = 1_000_000
    namespaces = CaptureNamespaces()

    def __init__(self, session, **kwargs):
        self.native_capture = capture_session(session, capacity=self.capacity,
            session_identity=self.namespaces.identity_for(session))
        super().__init__(self.native_capture, **kwargs)

    def run(self, *args, **kwargs):
        previous_proxy, previous_names = bundles._PolicySessionProxy, bundles.NATIVE_OWNER_CALLS
        if getattr(type(self.native_capture), "observe_protocol_control_policy_recent", None) is not None:
            bundles._PolicySessionProxy = _RecentBundleProxy
        bundles.NATIVE_OWNER_CALLS = previous_names | {
            "observe_protocol_control_policy_recent", "protocol_planning_snapshots"}
        try:
            part = super().run(*args, **kwargs)
        except BaseException:
            try:
                self.native_capture.take_completed()
            except BaseException as export_error:
                self.native_capture.errors.append("offline_export:" + str(export_error))
            raise
        finally:
            bundles._PolicySessionProxy, bundles.NATIVE_OWNER_CALLS = previous_proxy, previous_names
        # The full controller return/output is already included in its window.
        # Evidence export must never occur inside an owner activation/native call.
        self.native_capture.take_completed()
        return part

    def ledger(self):
        result = super().ledger()
        result["native_timing"] = {"batches": self.native_capture.batches,
            "call_envelopes": self.native_capture.envelopes, "capture_errors": self.native_capture.errors}
        return result


def analyze_phase_bundles(ledger):
    report = bundles.analyze_bundles(ledger)
    native = ledger.get("native_timing", {})
    partition = analyze_native_timing(native.get("batches", []), native.get("call_envelopes", []))
    if native.get("capture_errors"):
        partition["status"] = "unknown"
        partition["errors"].extend(native["capture_errors"])
    report["native_phase_partition"] = partition
    report["coarse_bundle_accounting_status"] = report["status"]
    if partition["status"] != "validated_partial_native_phase_partition":
        report["status"] = "unknown_native_phase_capture"
    return report


@contextmanager
def installed_driver():
    saved = driver.BundleRecorder, driver.analyze_bundles, driver.SOURCE_NAMES
    previous_namespaces = NativePhaseBundleRecorder.namespaces
    NativePhaseBundleRecorder.namespaces = CaptureNamespaces()
    driver.BundleRecorder, driver.analyze_bundles = NativePhaseBundleRecorder, analyze_phase_bundles
    driver.SOURCE_NAMES = (*driver.SOURCE_NAMES, "profile_native_request_timing.py",
        "capture_native_request_timing.py", "native_request_timing.py")
    try:
        yield
    finally:
        driver.BundleRecorder, driver.analyze_bundles, driver.SOURCE_NAMES = saved
        NativePhaseBundleRecorder.namespaces = previous_namespaces


def verify_build_receipt(path, binary, expected_sha):
    receipt = json.loads(path.read_text(encoding="utf-8"))
    schema = receipt.get("schema")
    archived_acceptance = schema == "g31.circulation.native_timing_accepted_build.v1"
    if (schema not in {"g31.circulation.clean_build.v1", "g31.circulation.native_timing_accepted_build.v1"} or
        receipt.get("status") != "passed" or receipt.get("source_changed") or
        not receipt.get("source_after") or receipt.get("source_before") != receipt["source_after"] or
        "cpp/ics_core/runtime/request_timing_recorder.hpp" not in {
            str(key).replace("\\", "/") for key in receipt["source_after"]}):
        raise ValueError("native_timing:unverified_build")
    expected_binary = next((value for key, value in receipt["binary_sha256"].items()
                            if Path(key).resolve() == binary.resolve()), None)
    if expected_binary != expected_sha or driver.sha(binary) != expected_sha:
        raise ValueError("native_timing:build_binary_identity_mismatch")
    root = Path(__file__).resolve().parents[3]
    if archived_acceptance:
        build_path = Path(receipt["build_receipt"])
        acceptance_path = Path(receipt["runtime_acceptance"])
        if (driver.sha(build_path) != receipt["build_receipt_sha256"] or
                driver.sha(acceptance_path) != receipt["runtime_acceptance_sha256"]):
            raise ValueError("native_timing:accepted_evidence_changed")
        build = json.loads(build_path.read_text(encoding="utf-8"))
        acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
        if (build.get("schema") != "g31.circulation.build_only.v1" or
                build.get("status") != "build_passed_tests_held" or build.get("source_changed") or
                build.get("source_before") != receipt["source_before"] or
                build.get("source_after") != receipt["source_after"] or
                build.get("binary_sha256") != receipt["binary_sha256"] or
                acceptance.get("schema") != "g31.native022_acceptance.v1" or acceptance.get("status") != "passed" or
                acceptance.get("runtime_cases_passed") != 16 or acceptance.get("compiled_source_changed") or
                acceptance.get("build_receipt_sha256") != receipt["build_receipt_sha256"] or
                acceptance.get("binary_sha256") != receipt["binary_sha256"] or
                acceptance.get("compiled_source_count") != len(receipt["source_after"]) or
                set(acceptance.get("cases", {})) != {"lost_ack", "original1x_prefix"} or
                any(case.get("ordered_raw_semantics_exact") is not True or
                    case.get("native_phase_report_recomputed") != "validated_partial_native_phase_partition"
                    for case in acceptance["cases"].values())):
            raise ValueError("native_timing:accepted_evidence_invalid")
        root = Path(receipt["compiled_source_archive"])
        if root.resolve() != Path(acceptance["source_archive"]).resolve():
            raise ValueError("native_timing:accepted_archive_mismatch")
    for relative, expected in receipt["source_after"].items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("native_timing:invalid_compiled_source_path")
        if driver.sha(root/relative) != expected:
            raise ValueError("native_timing:compiled_source_changed:" + relative)
    return receipt


def worker(args):
    receipt = verify_build_receipt(args.native_build_receipt, args.binary, args.expected_binary_sha256)
    NativePhaseBundleRecorder.capacity = args.native_trace_capacity
    driver.atomic(args.output/"native_timing_contract.json", {
        "schema": "g31.native_request_timing_capture_contract.v1", "build_receipt": str(args.native_build_receipt.resolve()),
        "build_receipt_sha256": driver.sha(args.native_build_receipt), "source_sha256": receipt["source_after"],
        "compiled_source_archive": receipt.get("compiled_source_archive"),
        "compiled_source_identity_scope": "accepted archived022 sources" if receipt.get("compiled_source_archive") else "live clean-build sources",
        "capacity_per_controller_call": args.native_trace_capacity,
        "scope": "Owner update coarse ledger plus partial native phase decomposition; no complete business request certificate.",
        "physics_subtracted": False, "full_native_coarse_charge_preserved": True,
        "diagnostic_export_outside_service_windows": True,
        "retained_trace_memory_can_affect_measured_overhead": True})
    with installed_driver():
        code = driver.worker(args)
    verify_build_receipt(args.native_build_receipt, args.binary, args.expected_binary_sha256)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--native-build-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--max-activations", type=int, default=5000)
    parser.add_argument("--activation-shard-budget", type=int, default=500)
    parser.add_argument("--event-budget", type=int, default=100000)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--native-trace-capacity", type=int, default=1_000_000)
    parser.add_argument("--verify-uninstrumented", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.max_activations, args.activation_shard_budget, args.event_budget,
           args.hard_timeout, args.native_trace_capacity) <= 0:
        raise ValueError("native_timing:invalid_budget")
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    started = time.perf_counter()
    with (args.output/"stdout.txt").open("w", encoding="utf-8") as stdout, (args.output/"stderr.txt").open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.hard_timeout, check=False)
            status, code = "finished", process.returncode
        except subprocess.TimeoutExpired:
            status, code = "hard_timeout", 124
    driver.atomic(args.output/"process.json", {"status": status, "exit_code": code, "command": command,
        "timeout_seconds": args.hard_timeout, "wall_seconds": time.perf_counter()-started, "maximum_native_workers": 1})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
