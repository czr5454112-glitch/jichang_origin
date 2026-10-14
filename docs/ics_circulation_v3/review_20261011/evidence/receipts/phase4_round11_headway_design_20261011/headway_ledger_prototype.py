"""Design-only entry ledger. Not imported by the ICS runtime or any planner.

This prototype has no trays, motion, scheduling permissions or simulation. Its
caller must supply authenticated physical entry events and authorized suffix IDs.
Passing its tests does not install or validate production headway support.
"""
from collections import defaultdict
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class EntryEvent:
    tray_id: str
    edge_id: str
    original_depart: int
    headway: int
    entered: bool = False

    def __post_init__(self):
        if not isinstance(self.tray_id, str) or not self.tray_id:
            raise ValueError("entry owner identity required")
        if not isinstance(self.edge_id, str) or not self.edge_id:
            raise ValueError("directed edge identity required")
        if type(self.original_depart) is not int or self.original_depart < 0:
            raise ValueError("nonnegative integer original departure required")
        if type(self.headway) is not int or self.headway <= 0:
            raise ValueError("positive integer headway required; zero emits no record")
        if type(self.entered) is not bool:
            raise ValueError("entered must be bool")

    @property
    def event_id(self):
        return self.tray_id, self.edge_id, self.original_depart

    @property
    def end(self):
        return self.original_depart + self.headway


def canonical(events, *, now=0):
    """Deduplicate descriptions, never merge different events of one tray."""
    if type(now) is not int or now < 0:
        raise ValueError("nonnegative integer clock required")
    by_id = {}
    for event in events:
        if not isinstance(event, EntryEvent):
            raise ValueError("typed entry event required")
        previous = by_id.get(event.event_id)
        if previous is not None:
            if previous.headway != event.headway:
                raise ValueError("same event has inconsistent immutable window")
            event = replace(event, entered=event.entered or previous.entered)
        by_id[event.event_id] = event
    return tuple(by_id[key] for key in sorted(by_id) if by_id[key].end > now)


def conflicts(events, *, now=0):
    """Capacity-one half-open sweep over event identities, not tray identities."""
    deltas = defaultdict(lambda: defaultdict(int))
    for event in canonical(events, now=now):
        deltas[event.edge_id][max(now, event.original_depart)] += 1
        deltas[event.edge_id][event.end] -= 1
    result = []
    for edge, values in sorted(deltas.items()):
        occupancy = 0
        for tick, delta in sorted(values.items()):
            occupancy += delta
            if occupancy > 1:
                result.append((edge, tick, occupancy))
    return tuple(result)


def record_actual_entry(events, event_id, *, now):
    """Only the actual cursor callback may use this; no time-based inference."""
    if type(now) is not int or now < 0:
        raise ValueError("nonnegative integer clock required")
    records = canonical(events, now=0)
    found = next((event for event in records if event.event_id == event_id), None)
    if found is None:
        raise ValueError("entry must match an accepted/frozen physical leg")
    if not found.entered and found.original_depart != now:
        raise ValueError("new actual entry notification must match its physical tick")
    return tuple(replace(event, entered=True) if event.event_id == event_id else event for event in records)


def retain_for_replacement(events, *, now, authorized_suffix_ids, frozen_prefix_ids):
    """No authorization is inferred here; the production owner must prove it.

    An entered event and an unentered frozen-prefix event keep their whole tail,
    even when it crosses the safe anchor. A future event outside the explicitly
    authorized suffix also remains committed. No end is clipped to the anchor.
    """
    authorized, frozen = set(authorized_suffix_ids), set(frozen_prefix_ids)
    return tuple(event for event in canonical(events, now=now)
                 if event.entered or event.event_id in frozen or event.event_id not in authorized)


def self_tail_signature(events, *, tray_id, tick):
    """Sufficient own entry history for this fixed-h prototype's future checks.

    This is not a license to discard real search labels or replace their paths.
    Frozen external commitments and all other physical state must also agree.
    """
    return tuple((event.edge_id, event.original_depart, event.end)
                 for event in canonical(events, now=tick) if event.tray_id == tray_id)
