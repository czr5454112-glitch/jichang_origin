"""Evidence-first audit helpers for the G4IRSF10 hand-off.

The previous scale matrix is useful evidence, but it only contains aggregate
rows.  In particular it has neither an arrival/departure time series nor a
declared service-level objective.  This module deliberately represents those
two gates as unverified instead of turning "all bags completed" into a
capacity claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


CORE_SCALE_SCENARIOS = tuple(
    f"high_flow_no_fault_{scale}x" for scale in (1, 2, 4, 8, 16)
)
REQUIRED_HARD_CASE_FAMILIES = ("high_flow", "fault", "tail")


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_jsonl(path: Path, limit: int | None = None) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if limit is not None and index >= limit:
                break
            if line.strip():
                yield json.loads(line)


def audit_high_flow_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Recalculate the scale evidence without inventing missing gates."""

    by_name = {str(row.get("scenario", "")): row for row in rows}
    audited: list[dict[str, Any]] = []
    for scenario in CORE_SCALE_SCENARIOS:
        row = by_name.get(scenario)
        if row is None:
            audited.append(
                {
                    "scenario": scenario,
                    "evidence_status": "MISSING",
                    "safe_execution_pass": False,
                    "queue_stability_status": "UNVERIFIED_NO_TIME_SERIES",
                    "service_level_status": "UNVERIFIED_NO_SLO",
                    "capacity_status": "FAIL_INCOMPLETE_EVIDENCE",
                }
            )
            continue

        planned = _integer(row.get("planned_segments"))
        raw_bags = _integer(row.get("raw_bags"))
        completed = _integer(row.get("complete_bags"))
        runtime_seconds = _number(row.get("runtime_seconds"))
        safe = (
            raw_bags > 0
            and completed == raw_bags
            and _integer(row.get("failed_segments")) == 0
            and _integer(row.get("node_conflicts")) == 0
            and _integer(row.get("runtime_full_astar_calls")) == 0
        )
        audited.append(
            {
                "scenario": scenario,
                "scale": row.get("scale", ""),
                "evidence_status": "RECORDED",
                "raw_bags": raw_bags,
                "complete_bags": completed,
                "planned_segments": planned,
                "mean_tth": _number(row.get("mean_tth")),
                "p95_tth": _number(row.get("p95_tth")),
                "p99_tth": _number(row.get("p99_tth")),
                "source_queue_backlog": _integer(row.get("source_queue_backlog")),
                "max_source_queue_delay": _number(row.get("max_source_queue_delay")),
                "loop_count": _integer(row.get("loop_count")),
                "fallback_calls": _integer(row.get("fallback_calls")),
                "fallback_per_planned_segment": (
                    _integer(row.get("fallback_calls")) / planned if planned else 0.0
                ),
                "segment_throughput_per_second": (
                    planned / runtime_seconds if runtime_seconds > 0.0 else 0.0
                ),
                "decision_count_status": "UNAVAILABLE_IN_G4IRSF10_TASK_ROWS",
                "fallback_per_decision": "",
                "decision_throughput_per_second": "",
                "safe_execution_pass": safe,
                # These fields are intentionally not inferred from the aggregate
                # count named source_queue_backlog.  The plan requires slope and
                # bounded drain time, neither of which is present in G4IRSF10.
                "queue_stability_status": "UNVERIFIED_NO_TIME_SERIES",
                "service_level_status": "UNVERIFIED_NO_SLO",
                "capacity_status": "UNVERIFIED",
            }
        )
    return audited


@dataclass(frozen=True)
class JsonlSpan:
    rows_used: int
    full_row_count: int
    min_pass_time: float | None
    max_pass_time: float | None
    elapsed_seconds: float
    copy_indices: tuple[int, ...]

    @property
    def coverage_fraction(self) -> float:
        return self.rows_used / self.full_row_count if self.full_row_count else 0.0


def audit_jsonl_span(path: Path, executed_limit: int) -> JsonlSpan:
    """Measure the rows the runtime actually consumed, not the generated tail."""

    pass_times: list[float] = []
    copy_indices: set[int] = set()
    full_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            if index < executed_limit:
                row = json.loads(line)
                pass_times.append(_number(row.get("pass_time")))
                if "generation_copy_index" in row:
                    copy_indices.add(_integer(row["generation_copy_index"]))
            full_count += 1
    minimum = min(pass_times) if pass_times else None
    maximum = max(pass_times) if pass_times else None
    return JsonlSpan(
        rows_used=len(pass_times),
        full_row_count=full_count,
        min_pass_time=minimum,
        max_pass_time=maximum,
        elapsed_seconds=(maximum - minimum) if minimum is not None and maximum is not None else 0.0,
        copy_indices=tuple(sorted(copy_indices)),
    )


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _case_fingerprint(row: Mapping[str, Any]) -> str:
    """Fingerprint content while ignoring run/case identifiers."""

    content = {
        "task_id": row.get("task_id"),
        "segment_id": str(row.get("segment_id", "")).split(":g4irsf10_c", 1)[0],
        "current_node": row.get("current_node"),
        "goal_node": row.get("goal_node"),
        "candidate_next_nodes": _json_list(row.get("candidate_next_nodes")),
        "selected_next": row.get("selected_next"),
        "decision_source": row.get("decision_source"),
        "fallback_reason": row.get("fallback_reason"),
        "path_history": _json_list(row.get("path_history")),
        "why_hard": sorted(str(item) for item in _json_list(row.get("why_hard"))),
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit_hard_case_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scenario_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    current_counts: Counter[str] = Counter()
    goal_counts: Counter[str] = Counter()
    fingerprints: Counter[str] = Counter()

    for row in rows:
        scenario = str(row.get("scenario", ""))
        scenario_counts[scenario] += 1
        current_counts[str(row.get("current_node", ""))] += 1
        goal_counts[str(row.get("goal_node", ""))] += 1
        fingerprints[_case_fingerprint(row)] += 1
        for category in _json_list(row.get("why_hard")):
            category_counts[str(category)] += 1

    coverage = {
        "high_flow": any("high_flow" in name for name in scenario_counts),
        "fault": any("fault" in name for name in scenario_counts),
        "tail": any(
            name in category_counts
            for name in ("high_tth_tail", "p95_or_p99_delay")
        ),
    }
    unique_count = len(fingerprints)
    summary = {
        "row_count": len(rows),
        "unique_content_count": unique_count,
        "duplicate_content_count": len(rows) - unique_count,
        "duplicate_rate": (len(rows) - unique_count) / len(rows) if rows else 0.0,
        "scenario_count": len(scenario_counts),
        **{f"covers_{family}": coverage[family] for family in REQUIRED_HARD_CASE_FAMILIES},
        "required_family_gate": all(coverage.values()),
    }
    distributions: list[dict[str, Any]] = []
    for dimension, counts in (
        ("scenario", scenario_counts),
        ("category", category_counts),
        ("current_node", current_counts),
        ("goal_node", goal_counts),
    ):
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            distributions.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "count": count,
                    "fraction": count / len(rows) if rows else 0.0,
                }
            )
    return summary, distributions


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write an empty evidence table: {path}")
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
