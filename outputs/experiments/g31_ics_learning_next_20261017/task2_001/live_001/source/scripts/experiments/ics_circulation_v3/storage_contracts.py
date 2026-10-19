"""Opt-in, publicly announced on-carrier storage for the common physical engine.

The waypoint is a finite, waitable node proxy, not a supplier EBS interface.
Ordinary Bag/Snapshot schemas remain unchanged. A storage bag retains its final
destination and tray throughout storage; only final unloading completes it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from .model import Bag, Snapshot


@dataclass(frozen=True)
class StorageWaypointContract:
    node_id: str
    release_at: int
    published_at: int
    evidence_status: str = "proxy"
    carrier_policy: str = "on_carrier"


@dataclass(frozen=True)
class StorageBag(Bag):
    storage: StorageWaypointContract | None = None


@dataclass(frozen=True)
class StorageProgress:
    tray_id: str
    contract: StorageWaypointContract
    arrived_at: int | None = None
    departed_at: int | None = None


@dataclass
class StorageSnapshot(Snapshot):
    storage_progress: dict[str, StorageProgress] = field(default_factory=dict)


@dataclass
class StoragePlanningSnapshot(StorageSnapshot):
    """Private frozen-prefix assumptions; never a live physical state."""
    projected_storage_progress: dict[str, StorageProgress] = field(default_factory=dict)


def storage_contract(snapshot, bag_id):
    bag = snapshot.bags.get(bag_id)
    return bag.storage if isinstance(bag, StorageBag) else None


def effective_storage_progress(snapshot, bag_id):
    if isinstance(snapshot, StoragePlanningSnapshot) and bag_id in snapshot.projected_storage_progress:
        return snapshot.projected_storage_progress[bag_id]
    return snapshot.storage_progress.get(bag_id) if isinstance(snapshot, StorageSnapshot) else None


def storage_state_payload(snapshot):
    if not isinstance(snapshot, StorageSnapshot):
        return {}
    value = {"storage_progress": {key: asdict(p) for key, p in snapshot.storage_progress.items()}}
    if isinstance(snapshot, StoragePlanningSnapshot):
        value["projected_storage_progress"] = {key: asdict(p) for key, p in snapshot.projected_storage_progress.items()}
    return value


def has_storage_contracts(snapshot):
    return isinstance(snapshot, StorageSnapshot) or any(isinstance(b, StorageBag) for b in snapshot.bags.values())


def reject_unsupported_storage(snapshot, future_bags=(), consumer="unsupported_consumer"):
    if has_storage_contracts(snapshot) or any(isinstance(b, StorageBag) for b in future_bags):
        raise ValueError(consumer + ":storage_contract_not_supported")


def storage_contract_failure(snapshot, bag_id):
    bag = snapshot.bags.get(bag_id)
    if not isinstance(bag, StorageBag):
        return None
    contract = bag.storage
    if not isinstance(contract, StorageWaypointContract):
        return "invalid_storage_contract"
    if not isinstance(snapshot, StorageSnapshot):
        return "storage_snapshot_required"
    if contract.carrier_policy != "on_carrier" or contract.evidence_status != "proxy":
        return "unsupported_storage_policy"
    if any(type(v) is not int or v < 0 for v in (contract.release_at, contract.published_at)):
        return "invalid_storage_time"
    if contract.published_at > bag.arrival or contract.published_at > snapshot.now:
        return "storage_contract_not_published"
    node = snapshot.network.nodes.get(contract.node_id)
    if node is None or not node.can_wait or contract.node_id == bag.destination:
        return "invalid_storage_waypoint"
    progress = effective_storage_progress(snapshot, bag_id)
    if progress is not None:
        if not isinstance(progress, StorageProgress) or progress.contract != contract:
            return "storage_progress_contract_mismatch"
        if progress.tray_id not in snapshot.trays:
            return "storage_progress_unknown_tray"
        if progress.arrived_at is None or type(progress.arrived_at) is not int or not bag.arrival <= progress.arrived_at <= snapshot.now:
            return "invalid_storage_arrival_record"
        if progress.departed_at is not None and (type(progress.departed_at) is not int
                or not max(progress.arrived_at, contract.release_at) <= progress.departed_at <= snapshot.now):
            return "invalid_storage_departure_record"
        if bag_id not in snapshot.completed:
            tray = snapshot.trays[progress.tray_id]
            if tray.bag_id != bag_id:
                return "storage_carrier_changed"
            # At a release-before-acquire tick the departing tray can already
            # have node=None. The movement observer records departure first.
            if progress.departed_at is None and tray.node != contract.node_id:
                plan = snapshot.plans.get(progress.tray_id)
                just_arrived = progress.arrived_at == snapshot.now and (
                    any(leg.arrive == snapshot.now and snapshot.network.edges[leg.edge_id].target == contract.node_id
                        for leg in plan.legs) if plan else False)
                just_arrived |= progress.arrived_at == snapshot.now and any(
                    flight.tray_id == progress.tray_id and flight.arrive == snapshot.now
                    and snapshot.network.edges[flight.edge_id].target == contract.node_id
                    for flight in snapshot.old_in_transit)
                if not just_arrived:
                    return "stored_carrier_left_without_event"
    return None


def storage_route_failure(snapshot, candidate):
    """Validate a full future witness from this physical/planning boundary."""
    reason = storage_contract_failure(snapshot, candidate.bag_id)
    if reason:
        return reason
    contract = storage_contract(snapshot, candidate.bag_id)
    if contract is None:
        return None
    progress = effective_storage_progress(snapshot, candidate.bag_id)
    if progress is not None and progress.tray_id != candidate.tray_id:
        return "storage_carrier_changed"
    if progress is not None and progress.departed_at is not None:
        return None
    node = snapshot.trays[candidate.tray_id].node
    if node == contract.node_id and progress is None:
        return "storage_ingress_event_missing"
    visited = progress is not None and progress.arrived_at is not None
    departed = False
    for leg in candidate.legs:
        edge = snapshot.network.edges.get(leg.edge_id)
        if edge is None:
            return "unknown_edge"
        if node == contract.node_id and visited:
            if leg.depart < contract.release_at:
                return "storage_release_not_reached"
            departed = True
        node = edge.target
        if node == contract.node_id:
            visited = True
    if not visited:
        return "storage_waypoint_required"
    if not departed:
        return "storage_departure_required"
    return None


def observe_storage_arrival(snapshot, tray_id, node, at):
    """Called only for actual entered-leg arrival or observed loaded presence."""
    tray = snapshot.trays[tray_id]
    contract = storage_contract(snapshot, tray.bag_id)
    if contract is None or node != contract.node_id:
        return False
    if not isinstance(snapshot, StorageSnapshot) or isinstance(snapshot, StoragePlanningSnapshot):
        raise ValueError("storage_physical_snapshot_required")
    previous = snapshot.storage_progress.get(tray.bag_id)
    if previous is None:
        snapshot.storage_progress[tray.bag_id] = StorageProgress(tray_id, contract, at)
        snapshot.version += 1
        return True
    if previous.tray_id != tray_id or previous.contract != contract:
        raise ValueError("storage_carrier_or_contract_changed")
    return False


def observe_storage_departure(snapshot, tray_id, edge, at):
    tray = snapshot.trays[tray_id]
    contract = storage_contract(snapshot, tray.bag_id)
    if contract is None or edge.source != contract.node_id:
        return False
    progress = snapshot.storage_progress.get(tray.bag_id)
    if progress is None or progress.tray_id != tray_id or progress.contract != contract:
        raise ValueError("storage_departure_without_ingress")
    if at < contract.release_at:
        raise ValueError("storage_release_not_reached")
    if progress.departed_at is None:
        snapshot.storage_progress[tray.bag_id] = replace(progress, departed_at=at)
        snapshot.version += 1
        return True
    return False


def project_storage_prefix(snapshot, planning, tray_id, frozen_legs):
    """Derive private stage assumptions only from the owner's frozen prefix."""
    contract = storage_contract(snapshot, snapshot.trays[tray_id].bag_id)
    if contract is None:
        return planning
    bag_id = snapshot.trays[tray_id].bag_id
    progress = effective_storage_progress(snapshot, bag_id)
    for leg in frozen_legs:
        edge = snapshot.network.edges[leg.edge_id]
        if edge.source == contract.node_id and progress is not None and progress.departed_at is None:
            if leg.depart < contract.release_at:
                raise ValueError("frozen_storage_release_violation")
            progress = replace(progress, departed_at=leg.depart)
        if edge.target == contract.node_id and progress is None:
            progress = StorageProgress(tray_id, contract, leg.arrive)
    values = dict(planning.__dict__)
    values.pop("projected_storage_progress", None)
    return StoragePlanningSnapshot(**values, projected_storage_progress={bag_id: progress} if progress else {})


def storage_committed_failure(snapshot, candidate):
    """Check surviving full/prefix history without pretending it is a new route.

    A committed prefix may stop before storage, but it must never leave storage
    early. A full plan must still satisfy the complete waypoint obligation.
    """
    reason = storage_contract_failure(snapshot, candidate.bag_id)
    if reason:
        return reason
    contract = storage_contract(snapshot, candidate.bag_id)
    if contract is None:
        return None
    progress = effective_storage_progress(snapshot, candidate.bag_id)
    tray = snapshot.trays.get(candidate.tray_id)
    if tray is None or (candidate.bag_id not in snapshot.completed and tray.bag_id != candidate.bag_id):
        return "storage_carrier_changed"
    if progress is not None and progress.tray_id != candidate.tray_id:
        return "storage_carrier_changed"
    # This entry also protects old/preinstalled plans and inventory readers,
    # which do not necessarily pass through the new-route validator. A string
    # of historical edges is not evidence that this carrier actually traversed
    # them. Check geometry, the current physical boundary and actual milestones.
    if tray.node == contract.node_id and progress is None:
        return "storage_ingress_event_missing"
    previous_edge = previous_leg = None
    active, past = [], []
    for leg in candidate.legs:
        edge = snapshot.network.edges.get(leg.edge_id)
        if edge is None:
            return "unknown_edge"
        if (type(leg.depart) is not int or type(leg.arrive) is not int
                or leg.depart < snapshot.bags[candidate.bag_id].arrival
                or leg.arrive != leg.depart + edge.travel_time):
            return "storage_plan_invalid_leg"
        if previous_leg and (previous_edge.target != edge.source or previous_leg.arrive > leg.depart):
            return "storage_plan_disconnected"
        if previous_leg and previous_leg.arrive < leg.depart and not snapshot.network.nodes[edge.source].can_wait:
            return "storage_plan_forbidden_wait"
        if leg.depart <= snapshot.now < leg.arrive:
            active.append((leg, edge))
        if leg.arrive <= snapshot.now:
            past.append((leg, edge))
        if edge.target == contract.node_id and leg.arrive < snapshot.now:
            if progress is None or progress.arrived_at > leg.arrive:
                return "storage_plan_missing_actual_ingress"
        if edge.source == contract.node_id and leg.depart < snapshot.now:
            if progress is None or progress.departed_at is None or progress.departed_at > leg.depart:
                return "storage_plan_missing_actual_departure"
        previous_edge, previous_leg = edge, leg
    if len(active) > 1:
        return "storage_plan_overlapping_legs"
    if active:
        leg, edge = active[0]
        if tray.node is not None and not (leg.depart == snapshot.now and tray.node == edge.source):
            return "storage_plan_physical_position_mismatch"
    elif candidate.legs:
        expected_node = past[-1][1].target if past else snapshot.network.edges[candidate.legs[0].edge_id].source
        just_arrived = tray.node is None and past and past[-1][0].arrive == snapshot.now
        if tray.node != expected_node and not just_arrived:
            return "storage_plan_physical_position_mismatch"
        next_leg = next((leg for leg in candidate.legs if leg.depart > snapshot.now), None)
        if next_leg is not None and not snapshot.network.nodes[expected_node].can_wait:
            return "storage_plan_forbidden_wait"
    visited = progress is not None or tray.node == contract.node_id
    departed = progress is not None and progress.departed_at is not None
    for leg in candidate.legs:
        edge = snapshot.network.edges.get(leg.edge_id)
        if edge is None:
            return "unknown_edge"
        if edge.source == contract.node_id:
            if leg.depart < contract.release_at:
                return "storage_release_not_reached"
            visited, departed = True, True
        if edge.target == contract.node_id:
            visited = True
    if candidate.prefix_only:
        return None
    if not visited:
        return "storage_waypoint_required"
    if not departed:
        return "storage_departure_required"
    final_node = (snapshot.network.edges[candidate.legs[-1].edge_id].target
                  if candidate.legs else tray.node)
    if final_node != snapshot.bags[candidate.bag_id].destination:
        return "storage_plan_wrong_final_destination"
    bag = snapshot.bags[candidate.bag_id]
    if bag.protected and candidate.unload_complete > bag.deadline:
        return "storage_plan_protected_deadline"
    if candidate.usable_at != candidate.unload_complete + snapshot.module.hold_ticks(final_node):
        return "storage_final_release_mismatch"
    if tray.mode in {"unloading", "holding"} and tray.available_at != candidate.usable_at:
        return "storage_service_state_mismatch"
    if candidate.legs:
        unload = candidate.legs[-1].arrive + snapshot.module.unload_ticks
        usable = unload + snapshot.module.hold_ticks(snapshot.bags[candidate.bag_id].destination)
        if candidate.unload_complete != unload or candidate.usable_at != usable:
            return "storage_final_release_mismatch"
    elif progress is not None and progress.departed_at is not None and candidate.unload_complete < progress.departed_at:
        return "storage_final_release_before_departure"
    elif not candidate.legs and tray.mode == "loaded" and candidate.unload_complete != snapshot.now + snapshot.module.unload_ticks:
        return "storage_final_release_mismatch"
    return None


def assert_storage_invariants(snapshot):
    if isinstance(snapshot, StoragePlanningSnapshot):
        raise AssertionError("private_storage_planning_view_is_not_physical")
    for bag_id, bag in snapshot.bags.items():
        if not isinstance(bag, StorageBag):
            continue
        reason = storage_contract_failure(snapshot, bag_id)
        assert reason is None, reason
        if bag_id in snapshot.completed:
            progress = effective_storage_progress(snapshot, bag_id)
            assert progress is not None and progress.departed_at is not None, "storage_completion_before_release"
            assert snapshot.completed[bag_id] >= progress.departed_at, "storage_completion_before_departure"
    if isinstance(snapshot, StorageSnapshot):
        assert all(isinstance(snapshot.bags.get(key), StorageBag) for key in snapshot.storage_progress), "orphan_storage_progress"
    for plan in snapshot.plans.values():
        reason = storage_committed_failure(snapshot, plan)
        assert reason is None, reason
    for flight in snapshot.old_in_transit:
        tray = snapshot.trays.get(flight.tray_id)
        if tray is None:
            continue  # General physical invariants diagnose the unknown tray.
        contract = storage_contract(snapshot, tray.bag_id)
        if contract is None:
            continue
        edge = snapshot.network.edges.get(flight.edge_id)
        assert edge is not None, "unknown_edge"
        if edge.source == contract.node_id or edge.target == snapshot.bags[tray.bag_id].destination:
            progress = effective_storage_progress(snapshot, tray.bag_id)
            assert progress is not None and progress.departed_at is not None, "storage_old_flight_without_release"
            assert progress.departed_at <= flight.depart, "storage_old_flight_precedes_release"
