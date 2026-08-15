#!/usr/bin/env python3
"""Run fresh F2 and A0+S4+J2+E2 on one canonical airport workload.

This is deliberately a thin runner: both arms consume the same protected
43,603-segment input in the same order, and only compact raw-bag timing
distributions plus runtime/safety counters are retained.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf13_runtime_profile as f2_profile
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf20_event_hotpath as g20
from scripts.eval.g4irsf11_fixed_map import (
    assert_canonical_map,
    canonical_graph_records,
)


SCHEMA = "czr005.g4irsf24.native_fresh_race.v1"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf24_native_fresh_race.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf24_native_fresh_race.csv"
DENOMINATORS = {
    "processed_attempt": "network_time_seconds",
    "java_release": "java_release_time_tth_seconds",
    "original_entry": "original_entry_time_tth_seconds",
}
HARD_SAFETY_ZERO_FIELDS = (
    "failed_count",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "unresolved_deadlock_count",
    "runtime_full_astar_calls",
    "runtime_full_cie_astar_calls",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "scorer_runtime_global_scan_count",
    "microphase_runtime_global_scan_count",
    "first_edge_credit_global_scan_count",
    "priority_future_route_input_count",
    "scorer_future_route_input_count",
    "first_edge_credit_future_route_count",
    "scorer_future_schedule_input_count",
    "full_future_routes_stored",
)
HARD_SAFETY_FALSE_FIELDS = (
    "event_limit_reached",
    "time_limit_reached",
    "bag_future_path_field_present",
    "full_cie_astar_runtime_fallback",
)


class NativeRaceError(RuntimeError):
    pass


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def apply_exact_hca_releases(
    prefix: harness.InputPrefix,
    release_csv: Path,
) -> tuple[harness.InputPrefix, dict[str, Any]]:
    """Replace canonical scheduled pass times with observed Java releases."""

    with release_csv.open("r", encoding="utf-8", newline="") as handle:
        lifecycle = list(csv.DictReader(handle))
    releases = {
        str(row["segment_id"]): float(row["release_epoch"])
        for row in lifecycle
    }
    selected_ids = {str(row["segment_id"]) for row in prefix.rows}
    missing = selected_ids - releases.keys()
    if missing:
        raise NativeRaceError(
            f"exact HCA release trace lacks {len(missing)} selected segments"
        )
    adjusted_rows: list[dict[str, Any]] = []
    deltas: list[float] = []
    for source in prefix.rows:
        row = dict(source)
        release = releases[str(row["segment_id"])]
        deltas.append(release - float(row["pass_time"]))
        row["pass_time"] = release
        adjusted_rows.append(row)
    adjusted = harness.InputPrefix(
        size_segments=prefix.size_segments,
        rows=tuple(adjusted_rows),
        prefix_sha256=prefix.prefix_sha256,
        raw_bag_count=prefix.raw_bag_count,
        first_segment_id=prefix.first_segment_id,
        last_segment_id=prefix.last_segment_id,
    )
    return adjusted, {
        "source": _portable_path(release_csv),
        "aligned_segment_count": len(adjusted_rows),
        "release_minus_canonical_pass_mean_seconds": statistics.fmean(deltas),
        "release_minus_canonical_pass_min_seconds": min(deltas),
        "release_minus_canonical_pass_max_seconds": max(deltas),
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise NativeRaceError("cannot summarize an empty timing population")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def timing_distributions(
    input_rows: Sequence[Mapping[str, Any]],
    bags: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    # The protected Java epoch conversion may release a segment up to one
    # second before its fractional raw-entry timestamp.  This is an audited
    # denominator property shared with the fresh HCA parser, not time travel.
    raw = harness.aggregate_raw_bag_timings(
        input_rows,
        bags,
        allow_release_before_original_entry=True,
    )
    if not raw or not all(bool(row["complete"]) for row in raw):
        raise NativeRaceError("fresh native arm did not complete every raw bag")
    result: dict[str, dict[str, Any]] = {}
    for denominator, field in DENOMINATORS.items():
        values = [float(row[field]) for row in raw]
        result[denominator] = {
            "count": len(values),
            "min_seconds": min(values),
            "mean_seconds": statistics.fmean(values),
            "median_seconds": statistics.median(values),
            "p95_seconds": _quantile(values, 0.95),
            "p99_seconds": _quantile(values, 0.99),
            "max_seconds": max(values),
        }
    return result, raw


def _compatible_safety(summary: Mapping[str, Any], requested: int) -> dict[str, Any]:
    """Check shared invariants without failing an older F2 ABI for absent fields."""

    gates = {
        "all_segments_completed": int(summary.get("completed_count", -1)) == requested,
        **{
            f"{name}_zero": int(summary[name]) == 0
            for name in HARD_SAFETY_ZERO_FIELDS
            if name in summary
        },
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "time_limit_not_reached": summary.get("time_limit_reached") is False,
    }
    for name in HARD_SAFETY_FALSE_FIELDS[2:]:
        if name in summary:
            gates[f"{name}_false"] = summary[name] is False
    return {"pass": all(gates.values()), "gates": gates}


def _strict_s4_safety(
    summary: Mapping[str, Any], requested: int
) -> dict[str, Any]:
    """Require the complete current hard-safety ABI for the current S4 arm."""

    required = (
        "completed_count",
        *HARD_SAFETY_ZERO_FIELDS,
        *HARD_SAFETY_FALSE_FIELDS,
    )
    missing = [name for name in required if name not in summary]

    def zero(name: str) -> bool:
        value = summary.get(name)
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) == 0.0
        )

    completed = summary.get("completed_count")
    gates = {
        "all_required_fields_present": not missing,
        "all_segments_completed": (
            isinstance(completed, (int, float))
            and not isinstance(completed, bool)
            and math.isfinite(float(completed))
            and float(completed) == float(requested)
        ),
        **{f"{name}_zero": zero(name) for name in HARD_SAFETY_ZERO_FIELDS},
        **{
            f"{name}_false": summary.get(name) is False
            for name in HARD_SAFETY_FALSE_FIELDS
        },
    }
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "missing_fields": missing,
    }


def _safety_for_arm(
    arm: str, summary: Mapping[str, Any], requested: int
) -> dict[str, Any]:
    if arm == "F2":
        return _compatible_safety(summary, requested)
    if arm == "S4":
        return _strict_s4_safety(summary, requested)
    raise NativeRaceError(f"unknown arm: {arm}")


def _run_arm(
    arm: str,
    *,
    repeat: int,
    prefix: harness.InputPrefix,
    binary: Path,
) -> dict[str, Any]:
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    if arm == "F2":
        request: dict[str, Any] = {
            "node_records": nodes,
            "edge_records": edges,
            "heuristic_time": heuristic,
            "bag_records": harness.binding_bag_records(prefix),
            "fault_windows": (),
            "scenario": f"g4irsf24_fresh_f2_r{repeat}",
            "summary_only": False,
            "trace_limit": 0,
            "event_trace_limit": 0,
            "expected_binary_path": binary,
            "search_path": binary.parent,
            **f2_profile._filtered_controls(),
        }
    elif arm == "S4":
        request = g20.build_native_request(
            prefix.rows,
            scale=1,
            policy="E2",
            binary=binary,
            root=ROOT,
            bounded_wall_seconds=60.0,
            check_events=65_536,
        )
        request["scenario"] = f"g4irsf24_fresh_s4_r{repeat}"
        request["trace_limit"] = 0
        request["event_trace_limit"] = 0
    else:
        raise NativeRaceError(f"unknown arm: {arm}")

    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary")
    bags = payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise NativeRaceError(f"{arm} payload lacks summary or bag rows")
    distributions, raw = timing_distributions(prefix.rows, bags)
    safety = _safety_for_arm(arm, summary, len(prefix.rows))
    if not safety["pass"]:
        raise NativeRaceError(f"{arm} hard-safety gate failed")
    return {
        "arm": arm,
        "repeat": repeat,
        "status": "PASS",
        "segments": len(prefix.rows),
        "raw_bags": len(raw),
        "timing": distributions,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "events_per_wall_second": (
                int(summary.get("event_count", 0)) / wall_seconds
                if wall_seconds > 0.0
                else None
            ),
        },
        "safety": safety,
        "runtime_tuple": {
            "resource_semantics": summary.get("resource_semantics_id"),
            "scorer": summary.get("scorer_id"),
            "pibt": summary.get("pibt_mode"),
            "event_semantics": summary.get("event_semantics"),
            "merge_timing": summary.get("merge_grant_timing_mode"),
            "hotpath": summary.get("g4irsf20_event_hotpath_policy", "E0"),
        },
    }


def run_race(
    *,
    f2_binary: Path,
    s4_binary: Path,
    release_csv: Path,
    repeats: int = 2,
    size_segments: int = harness.FULL_SIZE_SEGMENTS,
) -> dict[str, Any]:
    if repeats < 1:
        raise NativeRaceError("repeats must be positive")
    canonical_prefix = harness.load_input_prefix(size_segments, root=ROOT)
    prefix, release_alignment = apply_exact_hca_releases(
        canonical_prefix, release_csv.resolve(strict=True)
    )
    runs = [
        _run_arm_subprocess(
            arm=arm,
            repeat=repeat,
            binary=(f2_binary if arm == "F2" else s4_binary).resolve(strict=True),
            size_segments=size_segments,
            release_csv=release_csv.resolve(strict=True),
        )
        for repeat in range(repeats)
        for arm in ("F2", "S4")
    ]
    return {
        "schema": SCHEMA,
        "protocol": {
            "input": "data/processed/tasks/inputdata.jsonl",
            "segment_count": len(prefix.rows),
            "raw_bag_count": prefix.raw_bag_count,
            "repeat_count": repeats,
            "arm_order": [row["arm"] for row in runs],
            "denominators": list(DENOMINATORS),
            "release_alignment": release_alignment,
        },
        "runs": runs,
    }


def _run_arm_subprocess(
    *,
    arm: str,
    repeat: int,
    binary: Path,
    size_segments: int,
    release_csv: Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--single-arm",
            "--arm",
            arm,
            "--repeat",
            str(repeat),
            "--binary",
            str(binary),
            "--size-segments",
            str(size_segments),
            "--release-csv",
            str(release_csv),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise NativeRaceError(
            f"{arm} repeat {repeat} failed: {completed.stderr or completed.stdout}"
        )
    try:
        value = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise NativeRaceError(f"{arm} child returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise NativeRaceError(f"{arm} child result is not an object")
    return value


def _csv_bytes(payload: Mapping[str, Any]) -> bytes:
    rows: list[dict[str, Any]] = []
    for run in payload["runs"]:
        for denominator, metrics in run["timing"].items():
            rows.append(
                {
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "denominator": denominator,
                    **metrics,
                    **run["runtime"],
                    "hard_safety_pass": run["safety"]["pass"],
                }
            )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--f2-binary", type=Path)
    parser.add_argument("--s4-binary", type=Path)
    parser.add_argument("--release-csv", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument(
        "--size-segments", type=int, default=harness.FULL_SIZE_SEGMENTS
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--single-arm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--arm", choices=("F2", "S4"), help=argparse.SUPPRESS)
    parser.add_argument("--repeat", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--binary", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.single_arm:
        if args.arm is None or args.binary is None:
            parser.error("--single-arm requires --arm and --binary")
        canonical_prefix = harness.load_input_prefix(args.size_segments, root=ROOT)
        prefix, _release_alignment = apply_exact_hca_releases(
            canonical_prefix, args.release_csv.resolve(strict=True)
        )
        print(
            json.dumps(
                _run_arm(
                    args.arm,
                    repeat=args.repeat,
                    prefix=prefix,
                    binary=args.binary.resolve(strict=True),
                ),
                allow_nan=False,
            )
        )
        return 0
    if args.f2_binary is None or args.s4_binary is None:
        parser.error("--f2-binary and --s4-binary are required")
    payload = run_race(
        f2_binary=args.f2_binary,
        s4_binary=args.s4_binary,
        release_csv=args.release_csv,
        repeats=args.repeats,
        size_segments=args.size_segments,
    )
    json_path = args.output_json if args.output_json.is_absolute() else ROOT / args.output_json
    csv_path = args.output_csv if args.output_csv.is_absolute() else ROOT / args.output_csv
    _write(
        json_path,
        (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
            "utf-8"
        ),
    )
    _write(csv_path, _csv_bytes(payload))
    print(json.dumps({"status": "PASS", "json": str(json_path), "csv": str(csv_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
