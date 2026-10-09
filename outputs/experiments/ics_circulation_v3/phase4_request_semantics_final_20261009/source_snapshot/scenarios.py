"""Twenty-four independent synthetic initializations, not operating days.

All times, capacities, module parameters and forecasts in this file are research
assumptions. The Nanning audit is kept separate and is never relabelled as this
six-node synthetic network.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from .evaluation import ForecastDemand, indexed_int
from .model import Bag, Edge, FixedLocalModule, InFlight, Network, Node, Snapshot, Tray


@dataclass(frozen=True)
class PilotScene:
    scene_id: str
    state: Snapshot
    forecasts: tuple[ForecastDemand, ...]
    factors: dict
    target_bag_id: str = "bag:initial"
    target_tray_id: str = "tray:loaded"
    horizon: int = 48

    def future(self, seed: int) -> tuple[Bag, ...]:
        future = []
        actual_at = self.factors["actual_nominal_demand_at"]
        for index in range(2):
            bag_id = f"bag:B:{index}"
            arrival = actual_at + index + indexed_int(seed, self.scene_id, bag_id, "arrival", -1, 1)
            future.append(Bag(bag_id, "B", "A", arrival, arrival + 12))
        if self.factors["shared_resource_competition"]:
            bag_id = "bag:C:competitor"
            arrival = 3 + indexed_int(seed, self.scene_id, bag_id, "arrival", 0, 1)
            future.append(Bag(bag_id, "C", "B", arrival, 11))
        return tuple(sorted(future, key=lambda bag: (bag.arrival, bag.bag_id)))


def small_network() -> Network:
    nodes = {
        name: Node(name, "domestic" if name in {"A", "J", "C"} else "international",
                   f"control:{partition}", capacity=8)
        for name, partition in (("A", 0), ("J", 1), ("C", 1), ("K", 2), ("L", 2), ("B", 3))
    }
    edges = [
        Edge("A-J", "A", "J", 2), Edge("J-B", "J", "B", 6),
        Edge("A-K", "A", "K", 4), Edge("K-B", "K", "B", 6),
        Edge("A-L", "A", "L", 6), Edge("L-B", "L", "B", 8),
        Edge("C-J", "C", "J", 1), Edge("B-A", "B", "A", 8),
        Edge("old-long", "A", "B", 30),
    ]
    return Network(nodes, {edge.edge_id: edge for edge in edges})


def pilot_scenes() -> tuple[PilotScene, ...]:
    scenes = []
    for index, (shortage, competition, regime, hold) in enumerate(product(
            (False, True), (False, True), ("near", "far", "reversal"), (0, 4))):
        scene_id = f"synthetic:{index:02d}"
        forecast_at = 11 if regime != "far" else 19
        actual_at = 19 if regime == "reversal" else forecast_at
        target = Bag("bag:initial", "A", "B", 0, 20, protected=True)
        old_arrival = 6 if index % 3 == 0 else 18
        trays = {
            "tray:loaded": Tray("tray:loaded", "A", "loaded", target.bag_id),
            "tray:C": Tray("tray:C", "C"),
            "tray:old": Tray("tray:old", None, "in_transit"),
        }
        if not shortage:
            for tray_index in range(2):
                tray_id = f"tray:B:{tray_index}"
                trays[tray_id] = Tray(tray_id, "B")
        state = Snapshot(
            now=0, network=small_network(), trays=trays, bags={target.bag_id: target},
            old_in_transit=(InFlight("tray:old", "old-long", old_arrival - 30, old_arrival),),
            module=FixedLocalModule(unload_ticks=1, hold_by_node={"B": hold}, reception_capacity=2),
            load_times={target.bag_id: 0},
        )
        forecasts = [ForecastDemand("B", forecast_at + i) for i in range(2)]
        if competition:
            forecasts.append(ForecastDemand("C", 3))
        scenes.append(PilotScene(scene_id, state, tuple(forecasts), {
            "initial_B_shortage": shortage,
            "shared_resource_competition": competition,
            "demand_regime": regime,
            "forecast_nominal_demand_at": forecast_at,
            "actual_nominal_demand_at": actual_at,
            "module_hold_ticks": hold,
            "old_arrival": old_arrival,
            "independence_unit": "synthetic_initialization",
        }))
    return tuple(scenes)
