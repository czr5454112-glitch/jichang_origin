"""Teacher junction-slice collection from shielded environment rollouts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from czr005.envs import IcsJunctionEnv
from czr005.envs.ics_junction_env import EnvRunInfo, PolicyFn
from czr005.sim_py.event_sim import EpisodeResult


@dataclass(frozen=True)
class TeacherSliceRun:
    slices: tuple[dict[str, Any], ...]
    result: EpisodeResult
    run_info: EnvRunInfo

    def summary(self) -> dict[str, float | int | bool]:
        metrics = self.result.metrics
        fallback_count = sum(1 for item in self.slices if item["shield_result"] == "fallback")
        unsafe_count = sum(1 for item in self.slices if item["unsafe_proposal"])
        return {
            "slice_count": len(self.slices),
            "planned_count": metrics.planned_count,
            "unplanned_count": metrics.unplanned_count,
            "reservation_conflicts": metrics.reservation_conflicts,
            "fallback_count": fallback_count,
            "unsafe_proposal_count": unsafe_count,
            "steps": self.run_info.steps,
            "truncated": self.run_info.truncated,
        }


def collect_teacher_slices(
    env: IcsJunctionEnv,
    policy: PolicyFn,
    seed: int | None = None,
    max_steps: int = 100_000,
    expert_source: str = "astar_guided_safe",
) -> TeacherSliceRun:
    obs, info = env.reset(seed=seed)
    slices: list[dict[str, Any]] = []
    total_reward = 0.0
    steps = 0
    terminated = False
    truncated = False

    while not terminated:
        if steps >= max_steps:
            truncated = True
            break
        proposed_action = policy(obs, info)
        slice_obs = obs
        next_obs, reward, terminated, truncated_step, step_info = env.step(proposed_action)
        total_reward += reward
        if truncated_step:
            truncated = True
        if step_info.get("executed_action") is not None:
            slices.append(
                _build_slice(
                    slice_id=len(slices),
                    obs=slice_obs,
                    proposed_action=proposed_action,
                    step_info=step_info,
                    reward=reward,
                    expert_source=expert_source,
                )
            )
        obs, info = next_obs, step_info
        steps += 1
        if truncated:
            break

    return TeacherSliceRun(
        slices=tuple(slices),
        result=env.episode_result(),
        run_info=EnvRunInfo(total_reward=total_reward, steps=steps, truncated=truncated),
    )


def collect_labeled_policy_slices(
    env: IcsJunctionEnv,
    behavior_policy: PolicyFn,
    expert_policy: PolicyFn,
    seed: int | None = None,
    max_steps: int = 100_000,
    expert_source: str = "astar_guided_safe",
    behavior_source: str = "behavior_policy",
) -> TeacherSliceRun:
    """Collect teacher labels on states visited by a behavior policy.

    This is a compact DAgger-style primitive for Phase5/Phase6 preparation:
    the behavior policy drives the environment, while the stored expert action
    is computed from the same observation before the behavior action executes.
    """

    obs, info = env.reset(seed=seed)
    slices: list[dict[str, Any]] = []
    total_reward = 0.0
    steps = 0
    terminated = False
    truncated = False

    while not terminated:
        if steps >= max_steps:
            truncated = True
            break
        behavior_action = behavior_policy(obs, info)
        expert_action = expert_policy(obs, info)
        slice_obs = obs
        next_obs, reward, terminated, truncated_step, step_info = env.step(behavior_action)
        total_reward += reward
        if truncated_step:
            truncated = True
        if step_info.get("executed_action") is not None:
            item = _build_slice(
                slice_id=len(slices),
                obs=slice_obs,
                proposed_action=behavior_action,
                step_info=step_info,
                reward=reward,
                expert_source=expert_source,
                expert_action=expert_action,
            )
            item["behavior_source"] = behavior_source
            slices.append(item)
        obs, info = next_obs, step_info
        steps += 1
        if truncated:
            break

    return TeacherSliceRun(
        slices=tuple(slices),
        result=env.episode_result(),
        run_info=EnvRunInfo(total_reward=total_reward, steps=steps, truncated=truncated),
    )


def write_teacher_manifest(path: str | Path, slices: tuple[dict[str, Any], ...]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for item in slices:
            fh.write(json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n")


def _build_slice(
    slice_id: int,
    obs: dict[str, Any],
    proposed_action: int,
    step_info: dict[str, Any],
    reward: float,
    expert_source: str,
    expert_action: int | None = None,
) -> dict[str, Any]:
    expert_action = int(step_info["executed_action"] if expert_action is None else expert_action)
    candidates = list(obs["candidates"])
    chosen = _candidate_by_index(candidates, expert_action)
    task_obs = dict(obs["task"])
    return {
        "slice_id": slice_id,
        "expert_source": expert_source,
        "segment_id": task_obs["segment_id"],
        "task_id": task_obs["task_id"],
        "decision_time": task_obs["ready_time"],
        "current": task_obs["current"],
        "goal": task_obs["goal"],
        "obs": task_obs,
        "candidate_edges": candidates,
        "action_mask": list(obs["action_mask"]),
        "proposed_action": proposed_action,
        "expert_action": expert_action,
        "expert_rank": _candidate_rank(candidates, expert_action),
        "expert_cost_to_goal": _expert_cost_to_goal(chosen),
        "future_delay": _future_delay(chosen, float(task_obs["deadline"])),
        "shield_result": "fallback" if step_info.get("shield_blocked") else "accepted",
        "unsafe_proposal": bool(step_info.get("unsafe_proposal")),
        "reward": reward,
        "reached_goal": bool(step_info.get("reached_goal")),
    }


def _candidate_by_index(candidates: list[dict[str, Any]], action_index: int) -> dict[str, Any]:
    for candidate in candidates:
        if int(candidate["index"]) == action_index:
            return candidate
    raise KeyError(f"unknown action index: {action_index}")


def _candidate_rank(candidates: list[dict[str, Any]], action_index: int) -> int:
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            not bool(candidate["safe"]),
            float(candidate["heuristic_to_goal"]),
            float(candidate["travel_time"]),
            int(candidate["index"]),
        ),
    )
    for rank, candidate in enumerate(ordered):
        if int(candidate["index"]) == action_index:
            return rank
    return len(ordered)


def _expert_cost_to_goal(candidate: dict[str, Any]) -> float:
    return float(candidate["travel_time"]) + float(candidate["heuristic_to_goal"])


def _future_delay(candidate: dict[str, Any], deadline: float) -> float:
    return max(0.0, float(candidate["node_end"]) - deadline)
