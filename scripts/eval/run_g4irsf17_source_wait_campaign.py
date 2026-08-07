#!/usr/bin/env python3
"""Collect matched native G17 source-wait telemetry for H5 and E4/off.

This is a deliberately small bridge around the frozen G16 closed-loop runner.
It changes no scheduling controls: the only new switch records mutually
exclusive blocker intervals at real source-admission attempts.  The resulting
JSON/CSV files feed ``g4irsf17_campaign.py diagnose-source-wait`` directly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import run_g4irsf16_closed_loop_canary as g16


DEFAULT_OUTPUT_DIR = ROOT / "outputs/runtime/g4irsf17_source_wait"
DEFAULT_RULE_BUNDLE = g16.DEFAULT_RULE_BUNDLE


class CollectionError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CollectionError(message)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _portable_binary_reference(path: Path) -> str:
    """Keep evidence provenance useful without publishing a workstation root."""

    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        parts = path.parts
        for index, part in enumerate(parts):
            if part.casefold().startswith("build_"):
                return Path(*parts[index:]).as_posix()
        return path.name


def validate_native_wait_payload(
    payload: Mapping[str, Any], *, mode: str, segments: int
) -> dict[str, Any]:
    summary = payload.get("summary")
    rows = payload.get("g4irsf17_source_wait_blockers")
    _require(isinstance(summary, Mapping), f"{mode}: native summary missing")
    _require(isinstance(rows, list), f"{mode}: source-wait rows missing")
    _require(
        summary.get("g4irsf17_source_wait_telemetry_enabled") is True,
        f"{mode}: source-wait telemetry was not enabled",
    )
    total = summary.get("g4irsf17_source_wait_interval_total_count")
    stored = summary.get("g4irsf17_source_wait_interval_stored_count")
    dropped = summary.get("g4irsf17_source_wait_interval_dropped_count")
    _require(type(total) is int and type(stored) is int and type(dropped) is int,
             f"{mode}: interval counters missing")
    _require(stored == len(rows), f"{mode}: stored interval count mismatch")
    _require(total == stored + dropped, f"{mode}: interval conservation failed")
    _require(dropped == 0, f"{mode}: blocker trace truncated")
    _require(
        summary.get("g4irsf17_source_wait_runtime_global_scan_count") == 0,
        f"{mode}: G17 telemetry performed a global scan",
    )
    hard_gates = g16._hard_gates(summary, segments, mode)
    _require(hard_gates["safety_pass"] is True, f"{mode}: frozen hard gate failed")
    reason_seconds = summary.get("g4irsf17_source_wait_reason_bag_seconds")
    _require(isinstance(reason_seconds, Mapping), f"{mode}: reason totals missing")
    return {
        "mode": mode,
        "segments": segments,
        "interval_count": total,
        "wait_bag_seconds": float(summary.get("g4irsf17_source_wait_bag_seconds", 0.0)),
        "reason_bag_seconds": dict(reason_seconds),
        "hard_gates": hard_gates,
    }


def collect_source_wait(
    *,
    binary: Path,
    segments: int,
    rule_bundle: Path = DEFAULT_RULE_BUNDLE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    telemetry_limit: int = 200_000,
    native_runner: Callable[..., Mapping[str, Any]] = g16._run_native,
) -> dict[str, Any]:
    _require(segments in g16.ALLOWED_SEGMENTS, "unsupported segment count")
    _require(telemetry_limit > 0, "telemetry_limit must be positive")
    binary = binary.resolve(strict=True)
    rule_bundle = rule_bundle.resolve(strict=True)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, Mapping[str, Any]] = {}
    validations: dict[str, dict[str, Any]] = {}
    raw_rows: dict[str, list[dict[str, Any]]] = {}
    raw_summaries: dict[str, dict[str, Any]] = {}
    prefix = g16.g12.load_input_prefix(segments, root=ROOT)
    for arm, mode in (("h5", "closed_loop"), ("off", "off")):
        payload = native_runner(
            binary=binary,
            segments=segments,
            mode=mode,
            rule_bundle=rule_bundle,
            trace_limit=1,
            enable_g4irsf17_source_wait_telemetry=True,
            g4irsf17_source_wait_trace_limit=telemetry_limit,
        )
        payloads[arm] = payload
        validations[arm] = validate_native_wait_payload(
            payload, mode=mode, segments=segments
        )
        rows, timing = g16._raw_bag_performance(
            prefix.rows, payload, segments=segments
        )
        raw_rows[arm] = rows
        raw_summaries[arm] = timing

    paths: dict[str, str] = {}
    for arm in ("h5", "off"):
        wait_path = output_dir / f"g4irsf17_{arm}_{segments}.source_wait.json"
        wait_rows = [
            {"arm": arm, **dict(row)}
            for row in payloads[arm]["g4irsf17_source_wait_blockers"]
        ]
        _write_json(
            wait_path,
            {
                "schema": "czr005.g4irsf17.source_wait_collection.v1",
                "arm": arm,
                "segments": segments,
                "summary": dict(payloads[arm]["summary"]),
                "g4irsf17_source_wait_blockers": wait_rows,
            },
        )
        raw_path = output_dir / f"g4irsf17_{arm}_{segments}.raw_bag_timings.csv"
        g16._write_csv(raw_path, raw_rows[arm])
        paths[f"{arm}_telemetry"] = _display_path(wait_path)
        paths[f"{arm}_raw_bags"] = _display_path(raw_path)

    manifest_path = output_dir / f"g4irsf17_source_wait_{segments}.collection.json"
    manifest = {
        "schema": "czr005.g4irsf17.source_wait_collection_manifest.v1",
        "status": "PASS",
        "segments": segments,
        "binary": _portable_binary_reference(binary),
        "arms": validations,
        "raw_bag_timing": raw_summaries,
        "artifacts": paths,
        "publication": {
            "raw_runtime_artifacts": "LOCAL_ONLY_NOT_DISTRIBUTED",
            "raw_runtime_patterns": [
                "outputs/runtime/g4irsf17_source_wait/*.source_wait.json",
                "outputs/runtime/g4irsf17_source_wait/*.raw_bag_timings.csv",
                "outputs/runstate/**",
            ],
            "committed_compact_evidence": [
                "outputs/tables/g4irsf17_source_wait_cause_ledger.csv",
                "outputs/tables/g4irsf17_source_wait_topology_attribution.csv",
                "outputs/reports/g4irsf17_source_wait_diagnosis.md",
            ],
            "note": (
                "Raw telemetry and resumable runstate stay local and are not "
                "distributed with the repository; the listed CSV/report "
                "outputs are the compact committable evidence."
            ),
        },
        "next_command": (
            "python scripts/eval/g4irsf17_campaign.py diagnose-source-wait "
            f"--telemetry {paths['h5_telemetry']} "
            f"--off-telemetry {paths['off_telemetry']} "
            f"--h5-bags {paths['h5_raw_bags']} "
            f"--off-bags {paths['off_raw_bags']} --force"
        ),
    }
    _write_json(manifest_path, manifest)
    manifest["manifest"] = _display_path(manifest_path)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--segments", type=int, choices=g16.ALLOWED_SEGMENTS, default=8192
    )
    parser.add_argument("--rule-bundle", type=Path, default=DEFAULT_RULE_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--telemetry-limit", type=int, default=200_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = collect_source_wait(
        binary=args.binary,
        segments=args.segments,
        rule_bundle=args.rule_bundle,
        output_dir=args.output_dir,
        telemetry_limit=args.telemetry_limit,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
