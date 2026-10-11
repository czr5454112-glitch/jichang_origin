"""Opt-in, engine-owned routing caches with cold-equivalent logical work.

The old process-global cache remains the default elsewhere. In this contract
cache hits save physical preprocessing but consume exactly the same logical
work units, one by one, as a cold build. Thus even a budget expiring part-way
through a cached operation has the same candidate/status/work result. Wall
deadlines are rejected, not represented as reproducible computation budgets.

Only RegionalCandidateGenerator and the known engine/slow factory entrances
are covered. Arbitrary external callbacks that construct unrelated planners
remain their owner's responsibility. Do not call one generator concurrently.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path


CACHE_CONTRACT = "isolated_replay_v1"


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class IsolatedTopologyCache:
    """Private memoized static objects. Deepcopy is the checkpoint operation."""
    def __init__(self, capacity=16):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Cache capacity must be a positive integer")
        self.capacity, self.entries = capacity, OrderedDict()

    def get(self, signature, consume, accounting):
        from .routing import _StaticTopology, _preprocessing_unit
        hit = signature in self.entries
        accounting["topology_cache_hit"] = hit
        if not hit:
            topology = _StaticTopology(signature, consume, cold_equivalent=True, accounting=accounting)
            # A budget failure never installs a partial graph.
            self.entries[signature] = topology
            if len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
        else:
            topology = self.entries[signature]
            for _ in range(topology.topology_work):
                _preprocessing_unit(consume, "topology_edges", accounting, reused=True)
        self.entries.move_to_end(signature)
        return self.entries[signature]

    def export(self):
        """JSON audit data, including LRU order and all completed memo entries."""
        entries = []
        for signature, topology in self.entries.items():
            entries.append({"network_signature": signature, "topology_work": topology.topology_work,
                "lower": [{"goal": goal, "distances": dict(values), "work": topology._lower_work[goal]}
                          for goal, values in sorted(topology._lower.items())],
                "local": [{"source": source, "distances": dict(values[0]), "witnesses": dict(values[1]),
                           "work": topology._local_work[source]} for source, values in sorted(topology._local.items())]})
        return {"schema": CACHE_CONTRACT, "capacity": self.capacity, "entries_lru_oldest_first": entries}


@dataclass(frozen=True)
class ReplayRegionalFactory:
    """Pure factory: every new generator owns a fresh private cache.

    No mutable cache or query budget lives in the factory stored by the base
    Simulation checkpoint. The persistent fast generator's warm cache is
    copied by that checkpoint; slow proposals create independent generators.
    """
    horizon: int
    expansion_limit: int
    static_path_limit: int
    dynamic_local: bool
    local_label_limit: int

    @classmethod
    def from_generator(cls, generator):
        from .routing import RegionalCandidateGenerator
        if type(generator) is not RegionalCandidateGenerator:
            raise ValueError("Cache replay requires an unwrapped RegionalCandidateGenerator")
        if generator.deadline_ms is not None:
            raise ValueError("Deterministic cache replay requires deadline_ms=None")
        return cls(**{name: getattr(generator, name) for name in cls.__dataclass_fields__})

    def __call__(self, horizon=None):
        from .routing import RegionalCandidateGenerator
        return RegionalCandidateGenerator(**{**asdict(self), "horizon": self.horizon if horizon is None else horizon},
            deadline_ms=None, cache_contract=CACHE_CONTRACT)


def _unwrap(generator):
    seen = set()
    while id(generator) not in seen:
        seen.add(id(generator))
        from .routing import RegionalCandidateGenerator
        if type(generator) is RegionalCandidateGenerator:
            return generator
        if hasattr(generator, "generator"):
            generator = generator.generator
        elif hasattr(generator, "inner"):
            generator = generator.inner
        else:
            break
    raise ValueError("Cannot identify the regional generator inside this wrapper")


def _contract_copy(contract, settings):
    result = deepcopy(contract)
    if not isinstance(result, dict) or "continuation" not in result:
        return result
    result["continuation"]["routing_cache_contract"] = deepcopy(settings)
    result["continuation"].setdefault("implementation_sha256", {})["routing_cache_contract.py"] = sha256(Path(__file__).read_bytes()).hexdigest()
    result["continuation_sha256"] = _digest(result["continuation"])
    result.pop("contract_sha256", None)
    result["contract_sha256"] = _digest(result)
    return result


def _replay_factory(factory):
    """Find a pure factory without replacing its accounting wrapper."""
    seen = set()
    while id(factory) not in seen:
        seen.add(id(factory))
        if isinstance(factory, ReplayRegionalFactory):
            return factory
        factory = getattr(factory, "inner_factory", getattr(factory, "inner", None))
        if factory is None:
            break
    return None


def enable_replay_cache(engine):
    """Bind before the first query, then let normal checkpoint/deepcopy restore.

    Apply before optional accounting wrappers. Restored already-enabled engines
    retain their existing cache. Wrapper factories must preserve the returned
    pure inner factory rather than rebuilding a legacy/global generator.
    """
    from .routing import RegionalCandidateGenerator
    generator = _unwrap(engine._generator)
    fast = ReplayRegionalFactory.from_generator(generator)
    if type(engine._generator) is not RegionalCandidateGenerator and generator.cache_contract != CACHE_CONTRACT:
        raise ValueError("Enable replay caching before wrapping query accounting")
    slow_factory = None
    slow = getattr(engine, "slow_controller", None)
    if slow is not None:
        controller = getattr(slow, "controller", None)
        if controller is None or not hasattr(controller, "generator_factory"):
            raise ValueError("Unknown slow controller; cache entrance cannot be attested")
        if getattr(controller, "planning_budget_ms", None) is not None:
            raise ValueError("Deterministic cache replay requires slow planning_budget_ms=None")
        slow_factory = _replay_factory(controller.generator_factory)
        if slow_factory is None:
            slow_factory = ReplayRegionalFactory.from_generator(controller.generator_factory())
    generator.enable_cache_contract()
    # Existing wrappers on an already-enabled engine are intentionally kept.
    if _replay_factory(engine.generator_factory) is None:
        engine.generator_factory = fast
    if slow is not None and _replay_factory(slow.controller.generator_factory) is None:
        slow.controller.generator_factory = slow_factory
    settings = {"schema": CACHE_CONTRACT, "logical_preprocessing": "cold_equivalent_per_query",
        "physical_cache": "generator_owned_deepcopy; pure_factory_creates_fresh_private_generator",
        "deadline_ms": None, "fast_factory": asdict(fast),
        "slow_factory": asdict(slow_factory) if slow_factory else None,
        "external_callback_scope": "only these entrances and propagated CursorSimulation public projections"}
    if hasattr(engine, "control_contract"):
        engine.control_contract = _contract_copy(engine.control_contract, settings)
    selector = getattr(engine, "route_selector", None)
    if hasattr(selector, "contract"):
        selector.contract = _contract_copy(selector.contract, settings)
    if hasattr(slow, "contract"):
        slow.contract = _contract_copy(slow.contract, settings)
    return deepcopy(settings)


def routing_cache_state(engine):
    """Read-only JSON evidence; supports wrappers exposing .generator/.inner."""
    generator = _unwrap(engine._generator)
    if generator.cache_contract != CACHE_CONTRACT:
        raise ValueError("Engine does not use the explicit replay cache contract")
    payload = generator._owned_topology_cache.export()
    return {"schema": CACHE_CONTRACT, "fast_generator_config": asdict(ReplayRegionalFactory.from_generator(generator)),
            "fast_cache": payload, "fast_cache_sha256": _digest(payload),
            "factory_cache_state": "none; each factory call owns a fresh cache",
            "checkpoint_owner": "SimulationCheckpoint.generator; copied transitively by CoverageCheckpoint"}


@dataclass(frozen=True)
class RoutingCacheCheckpoint:
    schema: str
    generator_config: dict
    cache: IsolatedTopologyCache


def capture_routing_cache(engine):
    """Private in-memory checkpoint, not a controller input or untrusted JSON."""
    generator = _unwrap(engine._generator)
    routing_cache_state(engine)  # Attest contract before exporting mutable data.
    return RoutingCacheCheckpoint(CACHE_CONTRACT, asdict(ReplayRegionalFactory.from_generator(generator)),
                                  deepcopy(generator._owned_topology_cache))


def restore_routing_cache(engine, checkpoint):
    """Restore only memo state; never restart physics, cursors or query work."""
    generator = _unwrap(engine._generator)
    if (not isinstance(checkpoint, RoutingCacheCheckpoint) or checkpoint.schema != CACHE_CONTRACT
            or generator.cache_contract != CACHE_CONTRACT
            or asdict(ReplayRegionalFactory.from_generator(generator)) != checkpoint.generator_config):
        raise ValueError("Routing cache checkpoint contract/configuration mismatch")
    generator._owned_topology_cache = deepcopy(checkpoint.cache)
