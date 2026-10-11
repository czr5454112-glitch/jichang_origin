"""Observable immediate-action semantics, opt-in for W3 feature ablation.

No node identity one-hot, arrival tape, sampled outcome, or retained conditional
suffix is treated as physical occupancy. Snapshot visibility is exactly that of
the existing centralized synthetic evaluator, not a new distributed permission.
"""
from math import isfinite

from .learning import TimedAnalyticEvaluator, shortest_edges
from .nonlinear_learning import PHYSICAL_FEATURE_NAMES
from .runtime import ExecutionValidator, effective_reservations


def physical_features(state, candidate, horizon, forecasts=(), *, route_mode="next_edge"):
    if route_mode not in {"next_edge", "whole_route"}:
        raise ValueError("unknown route mode")
    if candidate.bag_id is None or candidate.bag_id not in state.bags:
        raise ValueError("physical routing features require an observed loaded task")
    prefix = (ExecutionValidator._safe_prefix(state, candidate)
              if route_mode == "next_edge" else candidate)
    tray = state.trays[candidate.tray_id]
    bag = state.bags[candidate.bag_id]
    end = state.network.edges[prefix.legs[-1].edge_id].target if prefix.legs else tray.node
    arrival = prefix.legs[-1].arrive if prefix.legs else state.now
    suffix = shortest_edges(state, end, bag.destination)
    # A candidate proposed as a complete legal witness must retain a path to
    # its task destination. Fail explicitly; zero must mean already there.
    if suffix is None:
        raise ValueError("candidate prefix has no directed path to its task destination")
    others = tuple(r for r in effective_reservations(state) if r.tray_id != tray.tray_id)
    node_occupants = {r.tray_id for r in others
                      if r.resource == f"node:{end}" and r.start <= arrival < r.end}
    occupied, ticks = 0., 0
    for leg in prefix.legs:
        capacity = state.network.edges[leg.edge_id].capacity
        if capacity <= 0:
            raise ValueError("physical prefix cannot traverse a closed edge")
        ticks += leg.arrive - leg.depart
        # Integrate unique other-tray occupancy in each half-open tick. This
        # handles adjacent/overlapping entries without counting a tray twice.
        for tick in range(leg.depart, leg.arrive):
            occupied += len({r.tray_id for r in others if r.resource == f"edge:{leg.edge_id}"
                             and r.start <= tick < r.end}) / capacity
    values = TimedAnalyticEvaluator(horizon, forecasts).features(state, candidate)
    values.update({
        "current_at_destination": float(tray.node == bag.destination),
        "prefix_completes_delivery": float(not prefix.prefix_only and end == bag.destination),
        "prefix_end_at_destination": float(end == bag.destination),
        "prefix_travel_ticks": float(ticks),
        "prefix_elapsed_ticks": float(arrival - state.now),
        "prefix_remaining_shortest_ticks": float(sum(state.network.edges[e].travel_time for e in suffix)),
        "prefix_end_headroom": float(state.network.nodes[end].capacity - len(node_occupants)),
        "prefix_edge_occupied_fraction": occupied / ticks if ticks else 0.,
    })
    if set(values) != set(PHYSICAL_FEATURE_NAMES) or not all(isfinite(v) for v in values.values()):
        raise ValueError("invalid physical feature schema")
    return values
