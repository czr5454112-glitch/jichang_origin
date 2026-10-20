"""Opt-in reuse of exact public occupancy-dependent regional A* paths.

This is separate from PublicTravel's static travel-time cache. A fresh handle
still owns each read-only observation. The bounded pool retains only immutable
public input keys and path tuples, never observations, jobs, ACKs or decisions.
Key construction, misses and maintenance are ordinary measured computation.
"""
from collections import OrderedDict
from contextlib import contextmanager
import math
import struct

from . import protocol_control
from .regional_control import _ObservationRouting as OriginalRouting


class _Unsupported(Exception):
    pass


def _sequence(value):
    if type(value) not in (list, tuple): raise _Unsupported
    return value


def _node(value):
    if type(value) is not int or not 0 <= value <= 2**31-1: raise _Unsupported
    return value


def _number(value):
    # Distinguish int/float and preserve float bits, including signed zero.
    if type(value) is int and abs(value) <= 2**53: return ("int", value)
    if type(value) is float and math.isfinite(value): return ("float64", struct.pack(">d", value))
    raise _Unsupported


def public_routing_key(observation):
    """Return a closed supported key domain, or None for exact old fallback.

    Original ordering is retained even for facts whose current arithmetic is
    order-insensitive. No weight rounding or alternative path solver is used.
    This must be called lazily, only when the original path method is needed.
    """
    try:
        if type(observation) is not dict: raise _Unsupported
        owner = observation["owner_id"]
        if type(owner) is not str or not owner: raise _Unsupported
        contracts = _sequence(observation["node_contracts"])
        records = _sequence(observation["node_records"])
        edges = _sequence(observation["edge_records"])
        if not 0 < len(contracts) <= 2048 or len(records) > 2048 or len(edges) > 16384: raise _Unsupported
        nodes, service = [], []
        for row in contracts:
            if type(row) is not dict: raise _Unsupported
            nodes.append((_node(row["node"]), "occupancy" in row, _number(row.get("occupancy", 0))))
        for row in records:
            _sequence(row)
            service.append((_node(row[0]), _number(row[2])))
        ids = frozenset(row[0] for row in nodes)
        if len(ids) != len(nodes) or len({r[0] for r in service}) != len(service) or {r[0] for r in service} != ids:
            raise _Unsupported
        travel = []
        for row in edges:
            _sequence(row)
            if len(row) != 4: raise _Unsupported
            u, v, length, speed = row
            u, v = _node(u), _node(v)
            if u not in ids or v not in ids: raise _Unsupported
            length_key, speed_key = _number(length), _number(speed)
            if speed <= 0 or length < 0 or not math.isfinite(length/speed): raise _Unsupported
            travel.append((u, v, length_key, speed_key))
        limits, faults = [], []
        edge_contracts = _sequence(observation["edge_contracts"])
        known_faults = _sequence(observation.get("known_faults", []))
        if len(edge_contracts) > 16384 or len(known_faults) > 16384: raise _Unsupported
        for row in edge_contracts:
            if type(row) is not dict: raise _Unsupported
            u, v = _node(row["from"]), _node(row["to"])
            if u not in ids or v not in ids: raise _Unsupported
            limits.append((u, v, _number(row["capacity"])))
        for row in known_faults:
            if type(row) is not dict or type(row["active"]) is not bool: raise _Unsupported
            u, v = _node(row["from"]), _node(row["to"])
            if u not in ids or v not in ids: raise _Unsupported
            faults.append((u, v, row["active"]))
        return ((owner, tuple(nodes), tuple(service), tuple(travel), tuple(limits), tuple(faults)), ids)
    except (_Unsupported, KeyError, IndexError, TypeError, ValueError, OverflowError):
        return None


class RegionalPathPool:
    """Bounded owner-isolated keys and LRU immutable paths; no checkpoint state."""
    def __init__(self, *, max_graphs=4, max_paths_per_graph=256):
        if any(type(n) is not int or n < 1 for n in (max_graphs, max_paths_per_graph)):
            raise ValueError("regional_path_pool:positive_integer_limits_required")
        self.max_graphs, self.max_paths_per_graph = max_graphs, max_paths_per_graph
        self._entries = OrderedDict()
        self.counts = dict(handles=0, key_builds=0, fallback_calls=0, local_hits=0,
            cross_activation_hits=0, path_misses=0, graph_evictions=0, path_evictions=0)

    def handle(self, observation):
        self.counts["handles"] += 1
        return _RoutingHandle(self, observation)

    def _graph(self, key):
        # Resolve the complete key exactly once per handle. Rehashing and
        # comparing it for every source/goal pair costs more than saved A* work.
        paths = self._entries.get(key)
        if paths is None:
            paths = OrderedDict()
            self._entries[key] = paths
        else:
            self._entries.move_to_end(key)
        if len(self._entries) > self.max_graphs:
            self._entries.popitem(last=False); self.counts["graph_evictions"] += 1
        return paths

    def _store(self, paths, pair, path):
        paths[pair] = path; paths.move_to_end(pair)
        if len(paths) > self.max_paths_per_graph:
            paths.popitem(last=False); self.counts["path_evictions"] += 1

    def snapshot(self):
        return dict(self.counts, resident_graphs=len(self._entries),
                    resident_paths=sum(len(rows) for rows in self._entries.values()))

    def clear(self):
        self._entries.clear()


class _RoutingHandle:
    def __init__(self, pool, observation):
        self._original = OriginalRouting(observation)
        self._pool = pool
        self._prepared = False
        self._key = self._nodes = None
        self._bucket = None
        self._paths = {}

    def path(self, observation, source, goal):
        original = self._original
        if type(observation) is not dict:
            self._pool.counts["fallback_calls"] += 1
            return original.path(observation, source, goal)
        # Preserve the original guard even for local or cross-activation hits.
        if observation is not original._observation or observation["now"] != original._now:
            return original.path(observation, source, goal)
        if type(source) is not int or type(goal) is not int:
            self._pool.counts["fallback_calls"] += 1
            return original.path(observation, source, goal)
        if not self._prepared:
            self._pool.counts["key_builds"] += 1
            result = public_routing_key(observation)
            self._prepared = True
            if result is not None: self._key, self._nodes = result
        if self._key is None or source not in self._nodes or goal not in self._nodes:
            self._pool.counts["fallback_calls"] += 1
            return original.path(observation, source, goal)
        pair = source, goal
        if pair in self._paths:
            self._pool.counts["local_hits"] += 1
            return self._paths[pair]
        if self._bucket is None:
            self._bucket = self._pool._graph(self._key)
        path = self._bucket.get(pair)
        if path is None:
            self._pool.counts["path_misses"] += 1
            path = original.path(observation, source, goal)
            # The old solver alone chooses the path; exceptions are never cached.
            self._pool._store(self._bucket, pair, path)
        else:
            self._pool.counts["cross_activation_hits"] += 1
            self._bucket.move_to_end(pair)
        self._paths[pair] = path
        return path


@contextmanager
def installed_regional_path_pool(*, max_graphs=4, max_paths_per_graph=256):
    """Serial process-local opt-in; frozen controller files remain unchanged.

    Existing controller contract requires each observation to be read-only
    during its handle's lifetime. Start a fresh context after fork/restore or
    between experimental arms; this is not a serialized policy dependency.
    """
    if protocol_control._ObservationRouting is not OriginalRouting:
        raise ValueError("regional_path_pool:another_installation_active")
    pool = RegionalPathPool(max_graphs=max_graphs, max_paths_per_graph=max_paths_per_graph)

    class InstalledRouting(_RoutingHandle):
        def __init__(self, observation):
            pool.counts["handles"] += 1
            super().__init__(pool, observation)

    protocol_control._ObservationRouting = InstalledRouting
    try:
        yield pool
    finally:
        changed = protocol_control._ObservationRouting is not InstalledRouting
        protocol_control._ObservationRouting = OriginalRouting
        pool.clear()
        if changed: raise RuntimeError("regional_path_pool:factory_changed_during_installation")
