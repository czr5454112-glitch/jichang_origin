"""Parser for the legacy Java ICS `inputdata.txt` task stream."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import cmp_to_key
import json
from pathlib import Path
from typing import Any, Iterable

EARLY_BAG_THRESHOLD_SECONDS = 4800.0
STORAGE_IN_GOAL = 47
STORAGE_OUT_START = 52
STORAGE_OUT_LEAD_SECONDS = 2700.0


@dataclass(frozen=True)
class RawLegacyTask:
    task_id: int
    entry_time: float
    std: float
    start: int
    end: int
    unloader: str | None
    loader: str | None
    source_line: int

    @property
    def slack_at_entry(self) -> float:
        return self.std - self.entry_time


@dataclass(frozen=True)
class ExpandedTask:
    segment_id: str
    task_id: int
    pallet_id: int
    pass_time: float
    std: float
    start: int
    goal: int
    original_start: int
    original_goal: int
    original_entry_time: float
    leg: str
    early_bag_split: bool
    source_line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_legacy_tasks(path: str | Path) -> tuple[str, tuple[RawLegacyTask, ...]]:
    task_path = Path(path)
    lines = task_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"empty task file: {task_path}")

    header = lines[0].strip()
    tasks: list[RawLegacyTask] = []
    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        parts = line.strip().split()
        if len(parts) < 5:
            raise ValueError(f"task line {line_no} must contain at least 5 fields")
        tasks.append(
            RawLegacyTask(
                task_id=int(parts[0]),
                entry_time=float(parts[1]),
                std=float(parts[2]),
                start=int(parts[3]),
                end=int(parts[4]),
                unloader=parts[5] if len(parts) > 5 else None,
                loader=parts[6] if len(parts) > 6 else None,
                source_line=line_no,
            )
        )
    return header, tuple(tasks)


def expand_tasks(
    raw_tasks: Iterable[RawLegacyTask],
    early_bag_threshold: float = EARLY_BAG_THRESHOLD_SECONDS,
    storage_in_goal: int = STORAGE_IN_GOAL,
    storage_out_start: int = STORAGE_OUT_START,
    storage_out_lead_seconds: float = STORAGE_OUT_LEAD_SECONDS,
) -> tuple[ExpandedTask, ...]:
    expanded: list[ExpandedTask] = []
    for raw in raw_tasks:
        is_direct = raw.slack_at_entry < early_bag_threshold
        if is_direct:
            expanded.append(
                ExpandedTask(
                    segment_id=f"{raw.task_id}:direct",
                    task_id=raw.task_id,
                    pallet_id=raw.task_id,
                    pass_time=raw.entry_time,
                    std=raw.std,
                    start=raw.start,
                    goal=raw.end,
                    original_start=raw.start,
                    original_goal=raw.end,
                    original_entry_time=raw.entry_time,
                    leg="direct",
                    early_bag_split=False,
                    source_line=raw.source_line,
                )
            )
            continue

        expanded.append(
            ExpandedTask(
                segment_id=f"{raw.task_id}:storage_in",
                task_id=raw.task_id,
                pallet_id=raw.task_id,
                pass_time=raw.entry_time,
                std=raw.std,
                start=raw.start,
                goal=storage_in_goal,
                original_start=raw.start,
                original_goal=raw.end,
                original_entry_time=raw.entry_time,
                leg="storage_in",
                early_bag_split=True,
                source_line=raw.source_line,
            )
        )
        expanded.append(
            ExpandedTask(
                segment_id=f"{raw.task_id}:storage_out",
                task_id=raw.task_id,
                pallet_id=raw.task_id,
                pass_time=raw.std - storage_out_lead_seconds,
                std=raw.std,
                start=storage_out_start,
                goal=raw.end,
                original_start=raw.start,
                original_goal=raw.end,
                original_entry_time=raw.entry_time,
                leg="storage_out",
                early_bag_split=True,
                source_line=raw.source_line,
            )
        )
    return tuple(expanded)


def group_tasks_by_start_java_order(tasks: Iterable[ExpandedTask]) -> dict[int, list[ExpandedTask]]:
    grouped: dict[int, list[ExpandedTask]] = {}
    for task in tasks:
        grouped.setdefault(task.start, []).append(task)
    for start, task_list in grouped.items():
        task_list.sort(key=cmp_to_key(_java_pass_time_comparator))
        grouped[start] = task_list
    return grouped


def summarize_tasks(raw_tasks: Iterable[RawLegacyTask], expanded: Iterable[ExpandedTask]) -> dict[str, Any]:
    raw = tuple(raw_tasks)
    expanded_tasks = tuple(expanded)
    direct = sum(1 for task in raw if task.slack_at_entry < EARLY_BAG_THRESHOLD_SECONDS)
    early = len(raw) - direct
    by_start: dict[int, int] = {}
    for task in expanded_tasks:
        by_start[task.start] = by_start.get(task.start, 0) + 1
    return {
        "schema": "czr005.legacy_tasks.summary.v1",
        "raw_task_count": len(raw),
        "direct_raw_task_count": direct,
        "early_split_raw_task_count": early,
        "expanded_task_count": len(expanded_tasks),
        "early_bag_threshold_seconds": EARLY_BAG_THRESHOLD_SECONDS,
        "storage_in_goal": STORAGE_IN_GOAL,
        "storage_out_start": STORAGE_OUT_START,
        "storage_out_lead_seconds": STORAGE_OUT_LEAD_SECONDS,
        "expanded_by_start": {str(k): v for k, v in sorted(by_start.items())},
    }


def write_task_jsonl(tasks: Iterable[ExpandedTask], output_path: str | Path) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for task in tasks:
            fh.write(json.dumps(task.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return out


def write_task_summary(summary: dict[str, Any], output_path: str | Path) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def _java_pass_time_comparator(left: ExpandedTask, right: ExpandedTask) -> int:
    return int(left.pass_time - right.pass_time)

