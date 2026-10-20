"""Opt-in phase-sidecar streaming; retained capture remains the default.

All controller/coarse-ledger behavior and complete native charges are inherited
unchanged. Only the exported native diagnostic graph can retire between calls.
Reconstruction/phase validation happen once after measured control and serial
replay, with the exact original native_timing schema saved for existing audits.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gc
import json
from pathlib import Path
import subprocess
import sys
import time

from . import profile_native_request_timing as retained
from .capture_native_request_timing import CaptureNamespaces, capture_session
from .stream_native_request_timing import streaming_capture_session, reconstruct_native_timing


driver, bundles = retained.driver, retained.bundles


class PhaseStorageRecorder(retained.NativePhaseBundleRecorder):
    stream_native_phase = False
    record_gc = False
    output = None
    instances = []

    def __init__(self, session, **kwargs):
        identity = self.namespaces.identity_for(session)
        if self.stream_native_phase:
            self.native_capture = streaming_capture_session(session, capacity=self.capacity,
                session_identity=identity, stream_directory=self.output/f"native_stream_{identity:04d}")
        else:
            self.native_capture = capture_session(session, capacity=self.capacity, session_identity=identity)
        bundles.BundleRecorder.__init__(self, self.native_capture, **kwargs)
        self.instances.append(self)
        self._gc_window = 0
        self._native_method = None
        self._gc_directory = self.output/f"gc_{identity:04d}"
        if self.record_gc:
            self._gc_directory.mkdir(exist_ok=False)

    def invoke(self, name, method, *args, **kwargs):
        previous = self._native_method
        self._native_method = name
        try:
            return super().invoke(name, method, *args, **kwargs)
        finally:
            self._native_method = previous

    def run(self, *args, **kwargs):
        self._gc_window += 1
        rows, pending, errors = [], {}, []
        def callback(phase, info):
            now = time.perf_counter_ns()
            generation = info["generation"]
            if phase == "start":
                if generation in pending:
                    errors.append("overlapping_gc_start")
                pending[generation] = {"start_ns": now, "generation": generation,
                    "root_request_id": self.current_root, "native_method": self._native_method}
            elif phase == "stop":
                start = pending.pop(generation, None)
                if start is None:
                    errors.append("gc_stop_without_start")
                else:
                    rows.append({**start, "end_ns": now, "wall_ns": now-start["start_ns"],
                        "collected": info.get("collected"), "uncollectable": info.get("uncollectable")})
        if self.record_gc:
            gc.callbacks.append(callback)
        try:
            part = super().run(*args, **kwargs)
        except BaseException:
            # Parent run attempts native take even on controller failure. Keep
            # invalid/exception evidence rather than replacing it with success.
            if self.stream_native_phase and self.native_capture.batches:
                try:
                    self.native_capture.flush()
                except BaseException as error:
                    self.native_capture.errors.append("offline_stream_export:" + str(error))
            raise
        finally:
            if self.record_gc:
                gc.callbacks.remove(callback)
                if pending:
                    errors.append("unfinished_gc_at_callback_removal")
                # Absolute perf-counter times permit exact offline intersection
                # with service/owner/native intervals. Never subtract them.
                driver.atomic(self._gc_directory/f"window_{self._gc_window:06d}.json.gz", {
                    "schema": "g31.native_phase_gc_window.v1", "window": self._gc_window,
                    "clock": "perf_counter_ns", "rows": rows, "errors": errors,
                    "callback_interval_includes_post_controller_native_export": True,
                    "gc_disabled_or_forced": False, "gc_time_subtracted": False}, compressed=True)
        if self.stream_native_phase:
            self.native_capture.flush()
        return part

    def ledger(self):
        if not self.stream_native_phase:
            return super().ledger()
        result = bundles.BundleRecorder.ledger(self)
        result["native_timing_stream"] = self.native_capture.stream.reference()
        result["native_timing_stream"]["unexported_batch_count"] = len(self.native_capture.batches)
        result["native_timing_stream"]["unexported_envelope_count"] = len(self.native_capture.envelopes)
        result["native_timing_stream"]["unexported_errors"] = list(self.native_capture.errors)
        if self.native_capture.batches or self.native_capture.envelopes or self.native_capture.errors:
            # A failed native take or failed disk commit must not leave only
            # counts in ledger_error_prefix. Preserve every buffered raw object
            # even though incomplete prefixes cannot validate as complete.
            result["native_timing_unexported"] = {"batches": self.native_capture.batches,
                "call_envelopes": self.native_capture.envelopes,
                "capture_errors": self.native_capture.errors}
        return result


def analyze_during_measurement(ledger):
    # Both storage arms defer this diagnostic phase audit. Otherwise a pair
    # would also compare repeated validator allocations against no validation.
    report = bundles.analyze_bundles(ledger)
    report["coarse_bundle_accounting_status"] = report["status"]
    report["native_phase_partition"] = {"status": "deferred_until_offline_reconstruction",
        "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}
    return report


@contextmanager
def installed_driver(args):
    saved = driver.BundleRecorder, driver.analyze_bundles, driver.SOURCE_NAMES
    attributes = ("capacity", "namespaces", "stream_native_phase", "record_gc", "output", "instances")
    previous = {name: getattr(PhaseStorageRecorder, name) for name in attributes}
    PhaseStorageRecorder.capacity = args.native_trace_capacity
    PhaseStorageRecorder.namespaces = CaptureNamespaces()
    PhaseStorageRecorder.stream_native_phase = args.stream_native_phase
    PhaseStorageRecorder.record_gc = args.record_gc
    PhaseStorageRecorder.output = args.output
    PhaseStorageRecorder.instances = []
    driver.BundleRecorder, driver.analyze_bundles = PhaseStorageRecorder, analyze_during_measurement
    driver.SOURCE_NAMES = (*driver.SOURCE_NAMES, "profile_native_request_timing.py",
        "capture_native_request_timing.py", "native_request_timing.py",
        "profile_streamed_native_timing.py", "stream_native_request_timing.py")
    try:
        yield PhaseStorageRecorder.instances
    finally:
        driver.BundleRecorder, driver.analyze_bundles, driver.SOURCE_NAMES = saved
        for name, value in previous.items():
            setattr(PhaseStorageRecorder, name, value)


def worker(args):
    overall_start = time.perf_counter_ns()
    receipt = retained.verify_build_receipt(args.native_build_receipt, args.binary, args.expected_binary_sha256)
    driver.atomic(args.output/"phase_storage_contract.json", {
        "schema": "g31.native_phase_storage_contract.v1", "stream_native_phase": args.stream_native_phase,
        "default_storage": "retained", "scope": "native_phase_sidecar_only",
        "native_build_receipt": str(args.native_build_receipt.resolve()),
        "native_build_receipt_sha256": driver.sha(args.native_build_receipt),
        "compiled_source_archive": receipt.get("compiled_source_archive"),
        "compiled_source_sha256": receipt["source_after"], "coarse_ledger_retained_in_memory": True,
        "record_gc": args.record_gc, "gc_disabled_or_forced": False,
        "physics_or_gc_subtracted": False, "full_native_coarse_charge_preserved": True,
        "complete_request_100ms_certified": False,
        "diagnostic_scope": "Native take, immutable sidecar writes, coarse ledger analysis/writes, and final reconstruction are evidence work outside returned controller service windows. Their process cost remains reported; required controller output serialization remains inside.",
        "retained_diagnostic_graph_can_still_affect_gc": "coarse ledger, namespace registry and native identity tables remain; stage1 streams only Python native envelope/span batches"})
    with installed_driver(args) as instances:
        code = driver.worker(args)
        if len(instances) != 1:
            raise ValueError("native_timing_stream:unexpected_session_count")
        recorder = instances[0]
        offline_start = time.perf_counter_ns()
        if args.stream_native_phase:
            reference = recorder.native_capture.seal()
            ledger = recorder.ledger()
            ledger["native_timing_stream"] = reference
            ledger["native_timing"] = reconstruct_native_timing(reference)
            # Reconstruct only now, after all measurement and plain replay.
            driver.atomic(args.output/"ledger.json.gz", ledger, compressed=True)
        else:
            ledger = recorder.ledger()
        report = retained.analyze_phase_bundles(ledger)
        driver.atomic(args.output/"accounting.json.gz", report, compressed=True)
        manifest = json.loads((args.output/"manifest.json").read_text(encoding="utf-8"))
        manifest.update(native_phase_storage="streamed" if args.stream_native_phase else "retained",
            native_phase_reconstruction_and_final_audit_ns=time.perf_counter_ns()-offline_start,
            accounting={key: value for key, value in report.items() if key != "requests"},
            complete_request_100ms_certified=False,
            worker_scope_through_final_audit_ns=time.perf_counter_ns()-overall_start)
        if args.stream_native_phase:
            manifest["native_timing_stream"] = reference
        if report["status"] != "complete_conservative_bundle_accounting":
            code = 2
        if manifest["source_changed"]:
            code = 2
        driver.atomic(args.output/"manifest.json", manifest)
    retained.verify_build_receipt(args.native_build_receipt, args.binary, args.expected_binary_sha256)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "binary", "native-build-receipt", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--max-activations", type=int, default=5000)
    parser.add_argument("--activation-shard-budget", type=int, default=500)
    parser.add_argument("--event-budget", type=int, default=100000)
    parser.add_argument("--hard-timeout", type=float, default=240.)
    parser.add_argument("--native-trace-capacity", type=int, default=1_000_000)
    parser.add_argument("--verify-uninstrumented", action="store_true")
    parser.add_argument("--stream-native-phase", action="store_true")
    parser.add_argument("--record-gc", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.max_activations, args.activation_shard_budget, args.event_budget,
           args.hard_timeout, args.native_trace_capacity) <= 0:
        raise ValueError("native_timing_stream:invalid_budget")
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
        "timeout_seconds": args.hard_timeout, "wall_seconds": time.perf_counter()-started,
        "maximum_native_workers": 1})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
