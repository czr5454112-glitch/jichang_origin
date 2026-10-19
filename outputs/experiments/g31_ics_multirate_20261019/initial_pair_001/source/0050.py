"""Finite frozen-obligation boundary probes, not an online safety authority.

The interval sweep is conventional capacity checking. Its purpose is to falsify
overbroad task-DAG closure and "current occupancy unchanged" arguments before
claiming a new solver. Native owner validation remains mandatory. Unmodelled
policy read-dependencies produce unknown, not a local-independence theorem.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class ObligationWindow:
    task: str
    resource: str
    start: float
    end: float
    amount: int = 1


def transitive_closure(seeds: Iterable[str], successors: dict[str, set[str]]) -> set[str]:
    reached = set(seeds)
    queue = list(reached)
    while queue:
        task = queue.pop()
        for next_task in successors.get(task, set()):
            if next_task not in reached:
                reached.add(next_task)
                queue.append(next_task)
    return reached


def capacity_violations(windows: Iterable[ObligationWindow], capacities: dict[str, int]) -> list[dict]:
    """Exact half-open interval check, release-before-acquire at equal time."""
    by_resource: dict[str, list[ObligationWindow]] = defaultdict(list)
    for window in windows:
        if not (math.isfinite(window.start) and math.isfinite(window.end)
                and window.start <= window.end and window.amount > 0):
            raise ValueError("boundary_reference:invalid_window")
        if window.resource not in capacities or capacities[window.resource] < 0:
            raise ValueError("boundary_reference:unknown_resource_capacity")
        if window.start < window.end:
            by_resource[window.resource].append(window)
    violations = []
    for resource, rows in by_resource.items():
        times = sorted({time for row in rows for time in (row.start, row.end)})
        for start, end in zip(times, times[1:]):
            active = [row for row in rows if row.start <= start < row.end]
            used = sum(row.amount for row in active)
            if used > capacities[resource]:
                violations.append({"resource": resource, "start": start, "end": end,
                                   "used": used, "capacity": capacities[resource],
                                   "tasks": sorted({row.task for row in active})})
    return violations


def compare_boundaries(baseline: list[ObligationWindow], patch: list[ObligationWindow], *,
                       changed_tasks: set[str], capacities: dict[str, int],
                       task_successors: dict[str, set[str]],
                       policy_read_successors: dict[str, set[str]] | None = None,
                       complete_hard_obligation_scope: bool = False) -> dict:
    """Compare task closure, conservative resource closure and exact slack.

    Return a repair *domain suggestion*, never a repaired solution. A nonempty
    conflict cannot be made feasible simply by renaming its users as mutable.
    Full repair must still be solved and replayed on the real native host.
    """
    if any(row.task not in changed_tasks for row in patch):
        raise ValueError("boundary_reference:patch_outside_changed_tasks")
    old_conflicts = capacity_violations(baseline, capacities)
    if old_conflicts:
        raise ValueError("boundary_reference:infeasible_baseline")
    exterior = [row for row in baseline if row.task not in changed_tasks]
    patched = exterior + patch
    conflicts = capacity_violations(patched, capacities)
    dag = transitive_closure(changed_tasks, task_successors)
    resource_users: dict[str, set[str]] = defaultdict(set)
    for row in baseline + patch:
        resource_users[row.resource].add(row.task)
    augmented = {key: set(value) for key, value in task_successors.items()}
    for users in resource_users.values():
        for task in users:
            augmented.setdefault(task, set()).update(users - {task})
    conservative = transitive_closure(changed_tasks, augmented)
    required = set(dag)
    for conflict in conflicts:
        required.update(conflict["tasks"])
    required = transitive_closure(required, task_successors)
    if policy_read_successors is not None:
        required = transitive_closure(required, policy_read_successors)
    certified = complete_hard_obligation_scope and not conflicts
    return {"task_dag_domain": sorted(dag), "resource_transitive_domain": sorted(conservative),
            "slack_checked_repair_domain": sorted(required), "conflicts": conflicts,
            "patch_capacity_status": "compatible_with_frozen_hard_windows" if certified else
                                     "conflict" if conflicts else "unknown_scope_incomplete",
            "external_policy_independence": "unknown" if policy_read_successors is None else
                                            "only_declared_read_graph_checked",
            "requires_native_replay": True, "patched_windows": [asdict(w) for w in patched],
            "novelty_status": "supporting_counterexample_and_standard_interval_baseline_not_new_method"}
