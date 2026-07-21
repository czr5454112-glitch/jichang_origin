"""Exact input and runtime-boundary audits for rolling G4IRSF11 cases."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence


_COPY_RE = re.compile(r"^(?P<base>.+):g4irsf11_c(?P<copy>\d+)(?::.+)?$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _identity(row: Mapping[str, Any]) -> tuple[str, int]:
    segment_id = str(row.get("segment_id") or "")
    match = _COPY_RE.fullmatch(segment_id)
    if match is None:
        raise ValueError(f"rolling segment_id has no copy identity: {segment_id!r}")
    copy_index = int(row.get("generation_copy_index", -1))
    encoded_copy = int(match.group("copy"))
    if copy_index != encoded_copy:
        raise ValueError(
            f"rolling copy mismatch for {segment_id}: field={copy_index}, encoded={encoded_copy}"
        )
    return match.group("base"), copy_index


def rolling_input_audit(
    workload_rows: Sequence[Mapping[str, Any]],
    *,
    expected_copies: int,
    offset_tolerance_seconds: float = 1.0e-6,
) -> dict[str, Any]:
    """Verify a complete base-segment x day-copy matrix and fixed offsets."""

    blockers: list[str] = []
    if expected_copies < 2:
        raise ValueError("rolling audit requires at least two copies")
    if not workload_rows:
        return {
            "status": "FAIL",
            "blockers": ["rolling workload is empty"],
            "expected_copy_count": expected_copies,
            "workload_row_count": 0,
        }

    by_base: dict[str, dict[int, float]] = {}
    seen_segments: set[str] = set()
    try:
        for row_index, row in enumerate(workload_rows):
            segment_id = str(row.get("segment_id") or "")
            if segment_id in seen_segments:
                blockers.append(f"duplicate segment_id:{segment_id}")
                continue
            seen_segments.add(segment_id)
            base, copy_index = _identity(row)
            release = _finite(row.get("release_time"), f"workload[{row_index}].release_time")
            copies = by_base.setdefault(base, {})
            if copy_index in copies:
                blockers.append(f"duplicate base/copy:{base}:c{copy_index}")
            copies[copy_index] = release
    except ValueError as exc:
        blockers.append(str(exc))

    expected_indices = set(range(expected_copies))
    missing_pairs = 0
    extra_pairs = 0
    strides: list[float] = []
    offset_mismatches = 0
    for base, copies in sorted(by_base.items()):
        actual = set(copies)
        missing_pairs += len(expected_indices - actual)
        extra_pairs += len(actual - expected_indices)
        if actual != expected_indices:
            continue
        base_release = copies[0]
        local_stride = copies[1] - base_release
        strides.append(local_stride)
        for copy_index in range(expected_copies):
            expected_release = base_release + copy_index * local_stride
            if abs(copies[copy_index] - expected_release) > offset_tolerance_seconds:
                offset_mismatches += 1

    stride = strides[0] if strides else 0.0
    if any(abs(value - stride) > offset_tolerance_seconds for value in strides):
        blockers.append("day stride differs between base segments")
    if strides and stride < 86_400.0 - offset_tolerance_seconds:
        blockers.append("rolling day stride is shorter than 86400 seconds")
    if missing_pairs:
        blockers.append(f"missing base/copy pairs:{missing_pairs}")
    if extra_pairs:
        blockers.append(f"unexpected base/copy pairs:{extra_pairs}")
    if offset_mismatches:
        blockers.append(f"nonlinear copy offsets:{offset_mismatches}")
    expected_rows = len(by_base) * expected_copies
    if len(workload_rows) != expected_rows:
        blockers.append(
            f"row count is not base_count*copy_count:{len(workload_rows)}!={expected_rows}"
        )

    coverage_rows = [
        [base, copy_index, copies.get(copy_index)]
        for base, copies in sorted(by_base.items())
        for copy_index in range(expected_copies)
    ]
    return {
        "status": "PASS" if not blockers else "FAIL",
        "blockers": sorted(set(blockers)),
        "workload_row_count": len(workload_rows),
        "base_segment_count": len(by_base),
        "expected_copy_count": expected_copies,
        "observed_copy_indices": sorted(
            {copy_index for copies in by_base.values() for copy_index in copies}
        ),
        "missing_base_copy_pair_count": missing_pairs,
        "unexpected_base_copy_pair_count": extra_pairs,
        "offset_mismatch_count": offset_mismatches,
        "day_stride_seconds": stride,
        "coverage_sha256": hashlib.sha256(_canonical(coverage_rows)).hexdigest(),
    }


def rolling_continuity_metrics(
    workload_rows: Sequence[Mapping[str, Any]],
    segment_rows: Sequence[Mapping[str, Any]],
    *,
    expected_copies: int,
    runtime_instance_id: str,
) -> dict[str, Any]:
    """Audit one runtime invocation across every rolling day boundary."""

    input_audit = rolling_input_audit(workload_rows, expected_copies=expected_copies)
    blockers = list(input_audit.get("blockers", []))
    workload = {str(row.get("segment_id") or ""): row for row in workload_rows}
    results = {str(row.get("segment_id") or ""): row for row in segment_rows}
    if len(workload) != len(workload_rows):
        blockers.append("workload segment IDs are not unique")
    if len(results) != len(segment_rows):
        blockers.append("runtime result segment IDs are not unique")
    missing_results = sorted(set(workload) - set(results))
    unknown_results = sorted(set(results) - set(workload))
    if missing_results:
        blockers.append(f"runtime omitted segments:{len(missing_results)}")
    if unknown_results:
        blockers.append(f"runtime returned unknown segments:{len(unknown_results)}")
    if not str(runtime_instance_id).strip():
        blockers.append("runtime_instance_id is missing")

    copy_starts: dict[int, float] = {}
    for row in workload_rows:
        try:
            _, copy_index = _identity(row)
            release = _finite(row.get("release_time"), "release_time")
        except ValueError as exc:
            blockers.append(str(exc))
            continue
        copy_starts[copy_index] = min(copy_starts.get(copy_index, release), release)

    boundaries: list[dict[str, Any]] = []
    for copy_index in range(1, expected_copies):
        if copy_index not in copy_starts:
            blockers.append(f"copy boundary missing:c{copy_index}")
            continue
        boundary = copy_starts[copy_index]
        prior_ids = []
        released_through_boundary_ids = []
        for segment_id, workload_row in workload.items():
            release = _finite(workload_row.get("release_time"), f"{segment_id}.release_time")
            if release < boundary:
                prior_ids.append(segment_id)
            if release <= boundary:
                released_through_boundary_ids.append(segment_id)

        def unfinished_at(segment_id: str) -> bool:
            result = results.get(segment_id)
            if result is None or not bool(result.get("completed", result.get("complete", False))):
                return True
            finish = _finite(result.get("finish_time"), f"{segment_id}.finish_time")
            return finish >= boundary

        pending_before = sum(unfinished_at(segment_id) for segment_id in prior_ids)
        pending_after = sum(
            unfinished_at(segment_id) for segment_id in released_through_boundary_ids
        )
        cross_boundary_completed = sum(
            bool(results.get(segment_id, {}).get("completed", results.get(segment_id, {}).get("complete", False)))
            and _finite(results[segment_id].get("finish_time"), f"{segment_id}.finish_time") >= boundary
            for segment_id in prior_ids
            if segment_id in results
        )
        boundaries.append(
            {
                "boundary_copy_index": copy_index,
                "boundary_time": boundary,
                "prior_released_count": len(prior_ids),
                "released_through_boundary_count": len(released_through_boundary_ids),
                "pending_before_boundary": pending_before,
                "pending_after_boundary": pending_after,
                "cross_boundary_completion_count": cross_boundary_completed,
            }
        )

    if len(boundaries) != expected_copies - 1:
        blockers.append(
            f"boundary evidence count mismatch:{len(boundaries)}!={expected_copies - 1}"
        )
    return {
        "status": "PASS" if not blockers else "FAIL",
        "blockers": sorted(set(blockers)),
        "runtime_instance_id": str(runtime_instance_id),
        "single_runtime_invocation_pass": bool(str(runtime_instance_id).strip()),
        "input_audit": input_audit,
        "boundary_count": len(boundaries),
        "boundaries": boundaries,
        "carry_over_observed": any(
            int(row["pending_before_boundary"]) > 0 for row in boundaries
        ),
        "cross_boundary_completion_count": sum(
            int(row["cross_boundary_completion_count"]) for row in boundaries
        ),
    }
