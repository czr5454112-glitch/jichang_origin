"""Bounded research cache of paths derived exclusively from public graph data.

Not installed in the frozen online controller. No jobs, trays, ACKs, resource
occupancy, forecast times or decisions are cached. PublicTravel is the exact
existing oracle; its immutable path tuples may be reused only under the same
ordered topology, service, travel times and resolved public closure set.
"""
from __future__ import annotations
from collections import OrderedDict
import math
from .analytic_control import PublicTravel


def graph_key(observation):
    owner = observation.get("owner_id")
    if type(owner) is not str or not owner:
        raise ValueError("travel_pool:declared_owner_required")
    now = observation["now"]
    service = tuple((int(r[0]), max(float(r[2]), .001)) for r in observation["node_records"])
    edges = tuple((int(u), int(v), float(length), float(speed))
                  for u, v, length, speed in observation["edge_records"])
    closed = {(int(e["from"]), int(e["to"])) for e in observation.get("edge_contracts", []) if int(e["capacity"]) <= 0}
    closed.update((int(f["from"]), int(f["to"])) for f in observation.get("known_faults", [])
                  if f.get("active", f.get("start", now) <= now < f.get("end", math.inf)))
    # Identical graph facts do not authorize sharing another owner's retained
    # work. Owner identity is part of the private cache boundary even when the
    # current effective topology happens to match exactly.
    return owner, service, edges, tuple(sorted(closed))


class PublicTravelPool:
    """Owner-isolated one-process LRU; never persisted in checkpoints.

    Each checkout returns fresh dictionaries so a caller cannot mutate another
    caller's service/edge-time view. The shared graph and search state remain
    private. This interface is restricted to PublicTravel's path/complete and
    service/edge_time reads used by the current analytic baseline.
    """
    def __init__(self, max_graphs=4):
        if type(max_graphs) is not int or max_graphs < 1:
            raise ValueError("travel_pool:positive_integer_capacity_required")
        self._capacity = max_graphs
        self._graphs = OrderedDict()
        self.hits = self.misses = 0

    def checkout(self, observation):
        key = graph_key(observation)
        graph = self._graphs.pop(key, None)
        if graph is None:
            graph = PublicTravel(observation)
            self.misses += 1
        else:
            self.hits += 1
        self._graphs[key] = graph
        while len(self._graphs) > self._capacity:
            self._graphs.popitem(last=False)
        return _TravelView(graph)


class _TravelView:
    def __init__(self, graph):
        self.__graph = graph
        self.service = graph.service.copy()
        self.edge_time = graph.edge_time.copy()

    def path(self, source, target):
        # Native analytical callers use declared graph nodes. Reject arbitrary
        # query identities so cached source/pair state is bounded by this graph.
        if source not in self.__graph.service or target not in self.__graph.service:
            raise ValueError("travel_pool:undeclared_node")
        return self.__graph.path(source, target)

    def complete(self, source, target):
        return self.path(source, target)[0] + self.service[target]
