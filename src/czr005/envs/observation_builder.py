"""Observation assembly for the junction-decision learning environment."""

from __future__ import annotations

from czr005.envs.action_mask import EdgeFaultWindow, action_mask, build_action_candidates
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg


def build_junction_observation(
    graph: IcsGraph,
    task: TaskLeg,
    current: int,
    ready_time: float,
    waiting_time: float,
    reservations: ReservationTable,
    edge_reservations: EdgeReservationTable,
    edge_capacity: int = 1,
    edge_headway_seconds: float = 0.0,
    fault_edges: set[tuple[int, int]] | None = None,
    fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
    hold_seconds: float = 1.0,
    require_reachable_goal: bool = True,
) -> dict[str, object]:
    candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=current,
        ready_time=ready_time,
        reservations=reservations,
        edge_reservations=edge_reservations,
        edge_capacity=edge_capacity,
        edge_headway_seconds=edge_headway_seconds,
        fault_edges=fault_edges,
        fault_windows=fault_windows,
        hold_seconds=hold_seconds,
        require_reachable_goal=require_reachable_goal,
    )
    current_node = graph.node(current)
    return {
        "task": {
            "segment_id": task.segment_id,
            "task_id": task.task_id,
            "pallet_id": task.pallet_id,
            "current": current,
            "goal": task.goal,
            "ready_time": ready_time,
            "deadline": task.std,
            "slack": task.std - ready_time,
            "waiting_time": waiting_time,
            "node_type": current_node.node_type,
            "out_degree": len(current_node.outgoing),
            "time_to_goal": graph.heuristic(current, task.goal),
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
        "action_mask": list(action_mask(candidates)),
    }
