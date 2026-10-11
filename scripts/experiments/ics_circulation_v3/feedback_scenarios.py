"""Factorial feedback mechanisms; declared synthetic, never held-out data."""
from dataclasses import dataclass

from .learning import RoutingDemandForecast
from .model import Bag, Edge, Network, Node, Snapshot, Tray


@dataclass(frozen=True)
class FeedbackScene:
    name: str
    initial: Snapshot
    forecasts: tuple
    future_bags: tuple
    horizon: int
    factors: dict


def feedback_scene(*, shared_travel=4, detour_extra=1, demand_shift=0, condition='matched'):
    if condition not in {'matched', 'no_demand', 'reversal'}:
        raise ValueError('unknown demand condition')
    nodes = {n: Node(n, 'B' if n == 'B' else 'A', 'left' if n in {'S', 'C', 'Y'} else 'right',
                     capacity=2, can_wait=n not in {'X', 'Y'}) for n in ('S', 'X', 'Y', 'G', 'C', 'B')}
    edges = [Edge('SX', 'S', 'X', shared_travel), Edge('XG', 'X', 'G', 2),
             Edge('SY', 'S', 'Y', shared_travel), Edge('YG', 'Y', 'G', 2 + detour_extra),
             Edge('CS', 'C', 'S', 1), Edge('XB', 'X', 'B', 1),
             Edge('BC', 'B', 'C', 2), Edge('GC', 'G', 'C', 2)]
    at = shared_travel + 2 + demand_shift
    initial = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                       {'loaded': Tray('loaded', 'S', 'loaded', 'initial'), 'donor': Tray('donor', 'C')},
                       {'initial': Bag('initial', 'S', 'G', 0, 30)})
    forecast = RoutingDemandForecast('need', 'B', 'C', at, at + 20)
    forecasts = () if condition == 'no_demand' else (forecast,)
    origin = 'C' if condition == 'reversal' else 'B'
    destination = 'G' if condition == 'reversal' else 'C'
    future = () if condition == 'no_demand' else (Bag('need:0', origin, destination, at, at + 20),)
    factors = {'shared_travel': shared_travel, 'detour_extra': detour_extra,
               'demand_shift': demand_shift, 'condition': condition,
               'source': 'synthetic_six_node_shared_corridor_single_route_deviation_mechanism',
               'prediction_error': 'origin_and_destination_switch_unpublished_until_real_arrival' if condition == 'reversal' else None,
               'node_capacity': 2, 'reception_capacity': 1, 'unload_ticks': 1,
               'no_wait_nodes': ['X', 'Y'], 'independent_confirmation': False}
    name = f'L{shared_travel}_D{detour_extra}_T{demand_shift}_{condition}'
    return FeedbackScene(name, initial, forecasts, future, 32, factors)


def feedback_matrix():
    return tuple(feedback_scene(shared_travel=length, detour_extra=extra, demand_shift=shift, condition=kind)
                 for length in (2, 4, 6) for extra in (1, 3) for shift in (-1, 0, 2)
                 for kind in ('matched', 'no_demand', 'reversal'))
