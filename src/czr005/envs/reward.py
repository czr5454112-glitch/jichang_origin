"""Reward helpers for shielded junction-decision experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionRewardConfig:
    elapsed_weight: float = 1.0
    wait_weight: float = 0.25
    shield_block_penalty: float = 2.0
    unsafe_proposal_penalty: float = 1.0
    goal_reward: float = 25.0
    late_penalty: float = 5.0
    unplanned_penalty: float = 25.0


def decision_reward(
    elapsed_seconds: float,
    waited_seconds: float = 0.0,
    reached_goal: bool = False,
    finish_time: float | None = None,
    deadline: float | None = None,
    shield_blocked: bool = False,
    unsafe_proposal: bool = False,
    unplanned: bool = False,
    config: DecisionRewardConfig | None = None,
) -> float:
    cfg = config or DecisionRewardConfig()
    reward = -cfg.elapsed_weight * elapsed_seconds
    reward -= cfg.wait_weight * waited_seconds
    if shield_blocked:
        reward -= cfg.shield_block_penalty
    if unsafe_proposal:
        reward -= cfg.unsafe_proposal_penalty
    if reached_goal:
        reward += cfg.goal_reward
        if finish_time is not None and deadline is not None and finish_time > deadline:
            reward -= cfg.late_penalty * (finish_time - deadline)
    if unplanned:
        reward -= cfg.unplanned_penalty
    return reward
