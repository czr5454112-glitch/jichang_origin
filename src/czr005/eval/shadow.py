"""Shadow-mode replay utilities for learned edge scorers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from czr005.envs import IcsJunctionEnv, shortest_safe_policy
from czr005.envs.ics_junction_env import PolicyFn
from czr005.models import EdgeScoreModel
from czr005.models.edge_score import featurize_slice


@dataclass(frozen=True)
class ShadowReplayResult:
    decisions: int
    disagreements: int
    unsafe_proposals: int
    safe_improvement_opportunities: int
    baseline_planned: int
    baseline_unplanned: int
    baseline_conflicts: int
    truncated: bool

    @property
    def disagreement_rate(self) -> float:
        return self.disagreements / self.decisions if self.decisions else 0.0

    @property
    def unsafe_proposal_rate(self) -> float:
        return self.unsafe_proposals / self.decisions if self.decisions else 0.0

    def to_dict(self) -> dict[str, float | int | bool]:
        return {
            "decisions": self.decisions,
            "disagreements": self.disagreements,
            "disagreement_rate": self.disagreement_rate,
            "unsafe_proposals": self.unsafe_proposals,
            "unsafe_proposal_rate": self.unsafe_proposal_rate,
            "safe_improvement_opportunities": self.safe_improvement_opportunities,
            "baseline_planned": self.baseline_planned,
            "baseline_unplanned": self.baseline_unplanned,
            "baseline_conflicts": self.baseline_conflicts,
            "truncated": self.truncated,
        }


def edge_score_policy_factory(model: EdgeScoreModel, safe_only: bool = True) -> PolicyFn:
    def policy(obs: dict[str, Any], info: dict[str, Any]) -> int:
        if not obs:
            return 0
        return model.predict_action(_model_item_from_obs(obs), safe_only=safe_only)

    return policy


def runtime_edge_score_policy_factory(
    runtime_model: Any | None,
    safe_only: bool = True,
    fallback_policy: PolicyFn | None = None,
) -> PolicyFn:
    def policy(obs: dict[str, Any], info: dict[str, Any]) -> int:
        if not obs:
            return 0
        if runtime_model is None:
            fallback = fallback_policy or shortest_safe_policy
            return fallback(obs, info)
        features, candidate_indices, action_mask = featurize_slice(_model_item_from_obs(obs))
        try:
            selected_position = int(runtime_model.predict(features, action_mask if safe_only else []))
        except (RuntimeError, ValueError):
            fallback = fallback_policy or shortest_safe_policy
            return fallback(obs, info)
        return candidate_indices[selected_position]

    return policy


def run_shadow_replay(
    env: IcsJunctionEnv,
    baseline_policy: PolicyFn,
    model: EdgeScoreModel,
    seed: int | None = None,
    max_steps: int = 100_000,
) -> ShadowReplayResult:
    obs, info = env.reset(seed=seed)
    decisions = 0
    disagreements = 0
    unsafe_proposals = 0
    safe_improvement_opportunities = 0
    terminated = False
    truncated = False

    while not terminated:
        if decisions >= max_steps:
            truncated = True
            break
        baseline_action = baseline_policy(obs, info)
        model_action = model.predict_action(_model_item_from_obs(obs), safe_only=False)
        if model_action != baseline_action:
            disagreements += 1
        if not _is_action_safe(obs, model_action):
            unsafe_proposals += 1
        elif _candidate_cost(obs, model_action) < _candidate_cost(obs, baseline_action):
            safe_improvement_opportunities += 1

        obs, _, terminated, truncated_step, info = env.step(baseline_action)
        decisions += 1
        if truncated_step:
            truncated = True
            break

    result = env.episode_result()
    summary = env.episode_summary()
    return ShadowReplayResult(
        decisions=decisions,
        disagreements=disagreements,
        unsafe_proposals=unsafe_proposals,
        safe_improvement_opportunities=safe_improvement_opportunities,
        baseline_planned=result.metrics.planned_count,
        baseline_unplanned=result.metrics.unplanned_count,
        baseline_conflicts=int(summary["post_shield_conflicts"]),
        truncated=truncated,
    )


def _model_item_from_obs(obs: dict[str, Any]) -> dict[str, Any]:
    return {
        "obs": obs["task"],
        "candidate_edges": obs["candidates"],
        "action_mask": obs["action_mask"],
        "goal": obs["task"]["goal"],
        "expert_action": 0,
    }


def _is_action_safe(obs: dict[str, Any], action: int) -> bool:
    for candidate in obs["candidates"]:
        if int(candidate["index"]) == action:
            return bool(candidate["safe"])
    return False


def _candidate_cost(obs: dict[str, Any], action: int) -> float:
    for candidate in obs["candidates"]:
        if int(candidate["index"]) == action:
            return float(candidate["travel_time"]) + float(candidate["heuristic_to_goal"])
    return float("inf")
