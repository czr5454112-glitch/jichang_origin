"""Learning-environment scaffolding for JunctionShield-MARL."""

from .action_mask import ActionCandidate, action_mask, build_action_candidates
from .ics_junction_env import (
    IcsJunctionEnv,
    astar_guided_policy_factory,
    fault_aware_astar_policy_factory,
    shortest_safe_policy,
)
from .observation_builder import build_junction_observation
from .reward import DecisionRewardConfig, decision_reward
from .vectorized_ics_env import VectorizedIcsEnv

__all__ = [
    "ActionCandidate",
    "DecisionRewardConfig",
    "IcsJunctionEnv",
    "VectorizedIcsEnv",
    "action_mask",
    "astar_guided_policy_factory",
    "build_action_candidates",
    "build_junction_observation",
    "decision_reward",
    "fault_aware_astar_policy_factory",
    "shortest_safe_policy",
]
