"""Run a historical native binary against one saved legacy request.

Keep a small exact per-bag result receipt instead of serializing another huge
native payload. This is a compatibility check, not an extra study arm.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from czr005 import cpp_backend


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bag_hash(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--old-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("choose a fresh receipt path")
    old_binary = args.old_binary.resolve(strict=True)
    reference = args.reference.resolve(strict=True)
    with gzip.open(reference / "request.json.gz", "rt", encoding="utf-8") as handle:
        request = json.load(handle)
    if request.get("s4_wait_estimator", "legacy") != "legacy":
        raise ValueError("reference must use the legacy scoring mode")
    with gzip.open(reference / "native_payload.json.gz", "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    expected = {row["segment_id"]: bag_hash(row) for row in payload["bags"]}
    if len(expected) != len(payload["bags"]):
        raise ValueError("duplicate reference bag identity")
    del payload
    old_sha = file_hash(old_binary)
    overrides = {"search_path": str(old_binary.parent), "expected_binary_path": str(old_binary)}
    request.update(overrides)
    started = time.perf_counter()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    elapsed = time.perf_counter() - started
    if payload["loaded_cpp_binary_sha256"] != old_sha:
        raise ValueError("historical comparison loaded the wrong binary")
    actual = {row["segment_id"]: bag_hash(row) for row in payload["bags"]}
    mismatches = sorted(key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key))
    receipt = {"schema": "g31.feng_alignment.historical_legacy_exact.v1",
               "reference_directory": str(reference), "request_sha256": file_hash(reference / "request.json.gz"),
               "reference_payload_sha256": file_hash(reference / "native_payload.json.gz"),
               "historical_binary": str(old_binary), "historical_binary_sha256": old_sha,
               "historical_binary_unchanged": file_hash(old_binary) == old_sha,
               "native_call_wall_seconds": elapsed, "changed_request_fields": sorted(overrides),
               "checked_segments": len(expected), "actual_segments": len(payload["bags"]),
               "all_bag_fields_exact": not mismatches and len(actual) == len(payload["bags"]),
               "mismatch_count": len(mismatches), "mismatch_segment_examples": mismatches[:20],
               "comparison": "SHA256 of every complete bag object, sorted JSON keys; no field exclusion",
               "scope": "default-mode compatibility; no extra physical/source constraints"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    if not receipt["all_bag_fields_exact"] or not receipt["historical_binary_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
