"""Query-local capacity calendars and mandatory-egress relaxed lower bounds.

These are not SIPP state dominance rules. Instantaneous node passage consumes
no interval in the runtime, and this module preserves that convention. Only a
positive-duration edge traversal is used by the storage egress lower bound.
"""
from bisect import bisect_right
from collections import defaultdict
from heapq import heappop, heappush

from .runtime import INFINITY, effective_reservations
from .routing_reference import EventTimeSearch


class CapacityCalendarView:
    """Effective public commitments, excluding only this candidate's tray.

    Calendar construction and every nonempty blocked-interval scan consume the
    caller's existing query budget. Calendars live for this query only. Empty
    calendar lookups use no interval scan; their containing label/projection
    work is already charged. Wall time includes effective_reservations itself.
    """

    def __init__(self, owner, snapshot, tray_id):
        self.owner, self.snapshot = owner, snapshot
        self.slots = defaultdict(list)
        self._blocked, self._ends = {}, {}
        for slot in effective_reservations(snapshot):
            owner._consume("storage_calendar_reservations")
            if slot.tray_id != tray_id:
                self.slots[slot.resource].append(slot)

    def blocked(self, resource):
        if resource not in self._blocked:
            kind, _, key = resource.partition(":")
            capacity = (self.snapshot.network.nodes[key].capacity if kind == "node" else
                        self.snapshot.network.edges[key].capacity if kind == "edge" else
                        self.snapshot.module.reception_capacity)
            if capacity <= 0:
                intervals = [(0, INFINITY)]
            else:
                deltas = defaultdict(int)
                for slot in self.slots[resource]:
                    self.owner._consume("storage_calendar_slot_index")
                    if slot.end > slot.start:
                        deltas[slot.start] += 1
                        deltas[slot.end] -= 1
                intervals, count, left = [], 0, None
                for tick, delta in sorted(deltas.items()):
                    self.owner._consume("storage_calendar_endpoints")
                    previous, count = count, count + delta
                    if previous < capacity <= count:
                        left = tick
                    elif previous >= capacity > count:
                        intervals.append((left, tick))
                        left = None
                # Runtime reservations have finite INFINITY endpoints, but
                # retaining this guard makes a malformed open tail fail closed.
                if left is not None:
                    intervals.append((left, INFINITY))
            self._blocked[resource] = tuple(intervals)
            self._ends[resource] = tuple(end for _, end in intervals)
        return self._blocked[resource]

    def available(self, resource, start, end):
        if end <= start:
            return True
        intervals = self.blocked(resource)
        index = bisect_right(self._ends[resource], start)
        if index == len(intervals):
            return True
        self.owner._consume("storage_calendar_interval_scans")
        return intervals[index][0] >= end

    def earliest_available(self, resource, start, duration):
        """First full interval at/after start; zero duration remains vacuous."""
        if duration <= 0:
            return start
        intervals = self.blocked(resource)
        index = bisect_right(self._ends[resource], start)
        tick = start
        for left, right in intervals[index:]:
            self.owner._consume("storage_calendar_interval_scans")
            if tick + duration <= left:
                break
            tick = max(tick, right)
            if tick >= INFINITY:
                return INFINITY
        return tick


class StorageCompletionLowerBound:
    """Necessary final-arrival bound with all edge calendars and relaxed waits.

    Every completion through storage traverses a suffix starting no earlier than
    release. This time-dependent Dijkstra retains edge capacities but permits
    arbitrary waiting at every node, ignoring node/reception/final-stock limits.
    Every real suffix is in this relaxed domain. Waiting makes the earliest-edge
    arrival function FIFO, so its earliest relaxed final arrival is a lower bound.
    This is a separate relaxation; it supplies no real-state dominance rule and
    never substitutes its paths for validated complete candidate witnesses.
    """

    def __init__(self, owner, topology, view, waypoint, destination, release):
        self.owner, self.topology, self.view = owner, topology, view
        self.waypoint, self.destination, self.release = waypoint, destination, release

    def earliest_final(self, earliest):
        earliest = max(earliest, self.release)
        distances, queue = {self.waypoint: earliest}, [(earliest, self.waypoint)]
        while queue:
            self.owner._consume("storage_relaxed_time_labels")
            tick, node = heappop(queue)
            if distances[node] != tick:
                continue
            if node == self.destination:
                return tick
            for target, travel, edge_id in self.topology.outgoing[node]:
                self.owner._consume("storage_relaxed_edge_scans")
                depart = self.view.earliest_available(f"edge:{edge_id}", tick, travel)
                arrive = depart + travel
                if arrive < distances.get(target, INFINITY):
                    distances[target] = arrive
                    heappush(queue, (arrive, target))
        return INFINITY


class StorageEventTimeSearch(EventTimeSearch):
    """Existing events plus storage's required-departure arrival events.

    Release and downstream reservation endpoints projected to storage departure
    are also possible storage arrival times. Reverse projection through an
    incoming no-wait chain lets a full storage node be crossed with zero dwell
    at such a time. This adds choices without merging exact-time labels or
    removing any old endpoint. It remains a bounded event representation.
    """

    def __init__(self, *args, waypoint, release):
        super().__init__(*args)
        self.waypoint, self.release = waypoint, release
        self._raw_projection_cache = {}

    def _events(self, node):
        if node not in self._raw_projection_cache:
            values, seen, storage_offsets = set(), set(), set()
            stack = [(node, 0)]
            while stack:
                current, offset = stack.pop()
                if (current, offset) in seen:
                    continue
                seen.add((current, offset))
                self.owner._consume("event_projection")
                for target, travel, edge_id in self.topology.outgoing[current]:
                    arrival_offset = offset + travel
                    if arrival_offset > self.limit - self.snapshot.now:
                        continue
                    if target == self.waypoint:
                        storage_offsets.add(arrival_offset)
                    for resource, shift in ((f"edge:{edge_id}", offset),
                                            (f"node:{target}", arrival_offset),
                                            (f"reception:{target}", arrival_offset)):
                        for slot in self.view.slots[resource]:
                            self.owner._consume("storage_event_calendar_scan")
                            values.add(slot.end - shift)
                    if not self.snapshot.network.nodes[target].can_wait:
                        stack.append((target, arrival_offset))
            self._raw_projection_cache[node] = (frozenset(values), frozenset(storage_offsets))
        return self._raw_projection_cache[node]

    def departures(self, node, tick):
        if not self.snapshot.network.nodes[node].can_wait:
            return (tick,)
        if node not in self._departures_cache:
            raw, offsets = self._events(node)
            values = set(raw)
            if offsets:
                # This is a second bounded projection of mandatory storage
                # events, not treating every occupied waitable node as no-wait.
                # The raw storage projection never recursively requests itself.
                storage_raw, _ = self._events(self.waypoint)
                arrivals = {self.release, *(t for t in storage_raw if self.release <= t <= self.limit)}
                for offset in offsets:
                    for arrival in arrivals:
                        self.owner._consume("storage_required_event_projection")
                        values.add(arrival - offset)
            self._departures_cache[node] = tuple(sorted(t for t in values if self.snapshot.now <= t <= self.limit))
        return tuple(sorted({tick, *(t for t in self._departures_cache[node] if t >= tick)}))
