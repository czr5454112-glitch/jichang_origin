"""Offline exact roundtrip of an existing retained sidecar; no native import."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

from .native_request_timing import analyze_native_timing
from .stream_native_request_timing import NativeTimingStream, reconstruct_native_timing, file_sha256


def _digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), ensure_ascii=True,
                                    allow_nan=False).encode()).hexdigest()


def verify(input_ledger, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    before = file_sha256(input_ledger)
    with gzip.open(input_ledger, "rt", encoding="utf-8") as handle:
        ledger = json.load(handle)
    native = ledger["native_timing"]
    batches, envelopes = native["batches"], native["call_envelopes"]
    store = NativeTimingStream(output/"stream", session_identity=batches[0]["session_identity"],
                               trace_epoch=batches[0]["trace_epoch"])
    cursor = 0
    for index, batch in enumerate(batches):
        stop = batch["completed_outer_calls"]
        store.append([batch], envelopes[cursor:stop], native["capture_errors"] if index == len(batches)-1 else [])
        cursor = stop
    if cursor != len(envelopes):
        raise ValueError("native_timing_stream:uncovered_input_envelopes")
    reference = store.seal(expected_call_count=len(envelopes), expected_batch_count=len(batches))
    actual = reconstruct_native_timing(reference)
    retained_report = analyze_native_timing(batches, envelopes)
    streamed_report = analyze_native_timing(actual["batches"], actual["call_envelopes"])
    after = file_sha256(input_ledger)
    checks = {"input_unchanged": before == after, "raw_exact_in_original_order": actual == native,
        "canonical_serialization_exact": _digest(actual) == _digest(native),
        "existing_validator_report_exact": retained_report == streamed_report,
        "existing_validator_accepts": retained_report["status"] == "validated_partial_native_phase_partition",
        "all_capture_errors_preserved": actual["capture_errors"] == native["capture_errors"]}
    receipt = {"schema": "g31.native_timing_stream_offline_roundtrip.v1",
        "status": "passed" if all(checks.values()) else "unknown", "checks": checks,
        "input_ledger": str(input_ledger.resolve()), "input_sha256_before": before, "input_sha256_after": after,
        "native_timing_sha256": _digest(native), "stream_reference": reference,
        "batches": len(batches), "envelopes": len(envelopes),
        "span_rows": sum(len(batch["rows"]) for batch in batches),
        "whole_native_envelope_ns": retained_report.get("unchanged_whole_native_envelope_ns"),
        "physics_subtracted_ns": 0, "native_workers": 0,
        "source_sha256": {str(path.resolve()): file_sha256(path) for path in
            (Path(__file__), Path(__file__).with_name("stream_native_request_timing.py"),
             Path(__file__).with_name("native_request_timing.py"))},
        "elapsed_offline_audit_ns": time.perf_counter_ns()-started,
        "scope": "Storage/reconstruction correctness on saved evidence only; no runtime speed, GC or complete-request certificate."}
    (output/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify(args.input_ledger, args.output)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
