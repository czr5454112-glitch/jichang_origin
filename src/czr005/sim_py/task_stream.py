"""Structured task stream for the Python reference simulator."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Iterator

from czr005.io.legacy_tasks import ExpandedTask, expand_tasks, parse_legacy_tasks


@dataclass(frozen=True)
class TaskLeg:
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

    @classmethod
    def from_expanded(cls, task: ExpandedTask) -> "TaskLeg":
        return cls(**task.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TaskLeg":
        return cls(
            segment_id=str(data["segment_id"]),
            task_id=int(data["task_id"]),
            pallet_id=int(data["pallet_id"]),
            pass_time=float(data["pass_time"]),
            std=float(data["std"]),
            start=int(data["start"]),
            goal=int(data["goal"]),
            original_start=int(data["original_start"]),
            original_goal=int(data["original_goal"]),
            original_entry_time=float(data["original_entry_time"]),
            leg=str(data["leg"]),
            early_bag_split=bool(data["early_bag_split"]),
            source_line=int(data["source_line"]),
        )

    def to_dict(self) -> dict[str, float | int | str | bool]:
        return {
            "segment_id": self.segment_id,
            "task_id": self.task_id,
            "pallet_id": self.pallet_id,
            "pass_time": self.pass_time,
            "std": self.std,
            "start": self.start,
            "goal": self.goal,
            "original_start": self.original_start,
            "original_goal": self.original_goal,
            "original_entry_time": self.original_entry_time,
            "leg": self.leg,
            "early_bag_split": self.early_bag_split,
            "source_line": self.source_line,
        }


class TaskStream:
    def __init__(self, tasks: Iterable[TaskLeg]) -> None:
        self._tasks = tuple(sorted(tasks, key=lambda task: (task.pass_time, task.task_id, task.leg)))

    @classmethod
    def from_legacy_input(cls, path: str | Path) -> "TaskStream":
        _, raw_tasks = parse_legacy_tasks(path)
        return cls(TaskLeg.from_expanded(task) for task in expand_tasks(raw_tasks))

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "TaskStream":
        tasks: list[TaskLeg] = []
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    tasks.append(TaskLeg.from_dict(json.loads(line)))
        return cls(tasks)

    def __iter__(self) -> Iterator[TaskLeg]:
        return iter(self._tasks)

    def __len__(self) -> int:
        return len(self._tasks)

    def first(self, count: int) -> tuple[TaskLeg, ...]:
        return self._tasks[:count]

    def until(self, end_time: float) -> tuple[TaskLeg, ...]:
        return tuple(task for task in self._tasks if task.pass_time <= end_time)

