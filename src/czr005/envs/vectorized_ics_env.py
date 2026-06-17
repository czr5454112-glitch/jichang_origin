"""Tiny vectorized wrapper for batches of junction-decision environments."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from czr005.envs.ics_junction_env import IcsJunctionEnv


class VectorizedIcsEnv:
    def __init__(self, env_fns: Sequence[Callable[[], IcsJunctionEnv]]) -> None:
        if not env_fns:
            raise ValueError("env_fns must not be empty")
        self.envs = [env_fn() for env_fn in env_fns]

    def reset(self, seed: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        observations: list[dict[str, Any]] = []
        infos: list[dict[str, Any]] = []
        for index, env in enumerate(self.envs):
            obs, info = env.reset(seed=None if seed is None else seed + index)
            observations.append(obs)
            infos.append(info)
        return observations, infos

    def step(
        self,
        actions: Sequence[int],
    ) -> tuple[list[dict[str, Any]], list[float], list[bool], list[bool], list[dict[str, Any]]]:
        if len(actions) != len(self.envs):
            raise ValueError("actions length must match env count")
        observations: list[dict[str, Any]] = []
        rewards: list[float] = []
        terminated: list[bool] = []
        truncated: list[bool] = []
        infos: list[dict[str, Any]] = []
        for env, action in zip(self.envs, actions):
            obs, reward, done, trunc, info = env.step(action)
            observations.append(obs)
            rewards.append(reward)
            terminated.append(done)
            truncated.append(trunc)
            infos.append(info)
        return observations, rewards, terminated, truncated, infos

    def episode_results(self) -> list[object]:
        return [env.episode_result() for env in self.envs]
