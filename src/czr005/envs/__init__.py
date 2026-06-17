"""Learning-environment scaffolding for JunctionShield-MARL."""

from .action_mask import (
    ActionCandidate,
    EdgeFaultWindow,
    action_mask,
    active_fault_edges,
    build_action_candidates,
)
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
    "EdgeFaultWindow",
    "IcsJunctionEnv",
    "VectorizedIcsEnv",
    "action_mask",
    "active_fault_edges",
    "astar_guided_policy_factory",
    "build_action_candidates",
    "build_junction_observation",
    "decision_reward",
    "fault_aware_astar_policy_factory",
    "shortest_safe_policy",
]
