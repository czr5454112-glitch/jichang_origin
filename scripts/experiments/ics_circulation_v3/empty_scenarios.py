"""Uncalibrated public-forecast scenario stress controller, development only.

The prior is the already declared synthetic development family.  It is not an
estimated airport posterior. No actual event tape or future publication enters
sampling. All current actions use common draws, with exact duplicate reuse.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from .empty_factorial import (EmptyFactorial, FactorialEmptyPrebalancer, SETTINGS,
                             build_empty_factorial_engine)
from .label_stability import sampled_futures
from .phase4_control import digest


@dataclass(frozen=True)
class PublicScenarioSettings:
    count: int = 8
    seed: int = 17

    def __post_init__(self):
        if type(self.count) is not int or self.count < 1 or type(self.seed) is not int:
            raise ValueError("positive scenario count and integer public seed required")


FACTORS = EmptyFactorial(continuation="timed_greedy", tie="fewest_physical")


def public_scenarios(snapshot, proxy, settings):
    """Only the point-forecast tape, never Simulation or private checkpoints."""
    proxy = tuple(proxy)
    if any(b.arrival <= snapshot.now or b.bag_id in snapshot.bags for b in proxy):
        raise ValueError("scenario input must be an unobserved future public proxy")
    if len({b.bag_id for b in proxy}) != len(proxy):
        raise ValueError("duplicate public proxy identity")
    # This prior includes OD reversal. Refuse incompatible topology instead of
    # silently generating unreachable bags or changing its probabilities.
    for bag in proxy:
        for source, target in ((bag.origin, bag.destination), (bag.destination, bag.origin)):
            seen, queue = {source}, [source]
            while queue:
                node = queue.pop()
                for edge in snapshot.network.edges.values():
                    if edge.source == node and edge.capacity > 0 and edge.target not in seen:
                        seen.add(edge.target)
                        queue.append(edge.target)
            if target not in seen:
                raise ValueError("OD reversal prior requires a positive-capacity return path")
    payload = {"schema": "public_synthetic_uncertainty_v1", "seed": settings.seed,
               "time": snapshot.now, "proxy": [asdict(b) for b in sorted(proxy, key=lambda b: b.bag_id)]}
    seed = int(digest(payload)[:16], 16)
    return sampled_futures(proxy, snapshot, count=settings.count, seed=seed)


class ScenarioEmptyPrebalancer(FactorialEmptyPrebalancer):
    def __init__(self, *args, scenarios=PublicScenarioSettings(), **kwargs):
        if not isinstance(scenarios, PublicScenarioSettings):
            raise TypeError("scenarios requires validated PublicScenarioSettings")
        self.scenarios = scenarios
        super().__init__(*args, factors=FACTORS, **kwargs)

    def _score(self, snapshot, sequence, forecasts, proxy, next_slow):
        futures = public_scenarios(snapshot, proxy, self.scenarios)
        physical, memo, requests = [], {}, []
        for future in futures:
            key = digest([asdict(b) for b in future])
            reused = key in memo
            if not reused:
                row = super()._score(snapshot, sequence, forecasts, future, next_slow)
                row["public_scenario_tape"] = [asdict(b) for b in future]
                row["public_scenario_sha256"] = key
                memo[key] = len(physical)
                physical.append(row)
            result = physical[memo[key]]
            requests.append({"future_sha256": key, "physical_index": memo[key], "cache_hit": reused,
                "status": result["status"], "proxy_cost": result["proxy_cost"]})
        complete = all(r["status"] == "complete" for r in physical)
        first = physical[0]
        row = {"status": "complete" if complete else "scenario_projection_incomplete",
            "proposals": [asdict(p) for p in sequence],
            "proxy_cost": sum(r["proxy_cost"] for r in requests) / len(requests) if complete else None,
            "scenarios": requests, "physical_scenarios": physical,
            "physical_proxy_calls": len(physical), "requested_scenarios": len(requests),
            "exact_duplicate_reuses": len(requests) - len(physical),
            "scenario_settings": asdict(self.scenarios),
            "search_calls": sum(r["search_calls"] for r in physical),
            "search_work": sum(r["search_work"] for r in physical),
            "ticks": sum(r["ticks"] for r in physical),
            "wall_seconds": sum(r["wall_seconds"] for r in physical),
            "cpu_seconds": sum(r["cpu_seconds"] for r in physical)}
        if complete:
            row["cost_components"] = {k: sum(physical[r["physical_index"]]["cost_components"][k]
                for r in requests) / len(requests) for k in first["cost_components"]}
            row["completed"] = sum(physical[r["physical_index"]]["completed"] for r in requests) / len(requests)
        return row

    def plan(self, snapshot, forecasts):
        plan = super().plan(snapshot, forecasts)
        plan.diagnostics.update(method="public_forecast_scenario_empty_control",
            scenario_settings=asdict(self.scenarios),
            prior="uncalibrated synthetic: cancel1/8,reverse1/8,otherwisekeep;jitter{-2,0,2};protected proxy units preserve OD/existence",
            action_objective="mean of all common requested scenario costs; duplicate multiplicity retained",
            budget_scope="max_rollouts counts action requests; each unique scenario has full branch budget; no extra actions unlocked by memo",
            prior_information="declared synthetic family additional model assumption; not operational calibration or true future access")
        return plan


def build_scenario_empty_engine(scene, *, scenarios=PublicScenarioSettings(), spec=None, settings=SETTINGS):
    engine = build_empty_factorial_engine(scene, FACTORS, spec=spec, settings=settings)
    prior = engine.slow_controller.controller
    engine.slow_controller.controller = ScenarioEmptyPrebalancer(spec=prior.spec, settings=settings,
        generator_factory=prior.generator_factory, scenarios=scenarios)
    contract = engine.control_contract
    contract["continuation"].update(prebalancer="ScenarioEmptyPrebalancer", public_scenarios=asdict(scenarios),
        forecast_uncertainty="uncalibrated synthetic prior, public inputs only, shared draws per action")
    contract["continuation"]["implementation_sha256"]["empty_scenarios.py"] = sha256(Path(__file__).read_bytes()).hexdigest()
    contract["continuation_sha256"] = digest(contract["continuation"])
    contract.pop("contract_sha256", None)
    contract["contract_sha256"] = digest(contract)
    engine.slow_controller.contract = engine.route_selector.contract = contract
    return engine
