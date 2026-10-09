"""Seeded synthetic sources for grouped learning and deployment evaluation.

These are new source groups, disjoint from the first 24 hand-designed cases.
Each has a common causal history to tick 2, before any uncertain future event.
"""
from dataclasses import dataclass, replace

from .evaluation import indexed_int
from .learning import RoutingDemandForecast
from .model import Bag, Edge, FixedLocalModule, InFlight, Network, Node, Snapshot, Tray


@dataclass(frozen=True)
class Phase2Scene:
    source_group: str
    split: str
    initial: Snapshot
    forecasts: tuple[RoutingDemandForecast, ...]
    truth_shift: int
    horizon: int = 72
    intervention_at: int = 2
    target_bag: str = "bag:target"
    target_tray: str = "tray:target"

    def future(self, seed: int) -> tuple[Bag, ...]:
        bags = []
        for forecast in self.forecasts:
            for index in range(forecast.count):
                bag_id = f"{forecast.forecast_id}:{index}"
                shift = self.truth_shift if forecast.node == "B" else 0
                at = forecast.at + shift + indexed_int(seed, self.source_group, bag_id, "arrival", -2, 2)
                # Service windows are fixed published deadlines in this proxy;
                # an arrival revision does not silently relax the deadline.
                bags.append(Bag(bag_id, forecast.node, forecast.destination, at, forecast.deadline))
        return tuple(sorted(bags, key=lambda b: (b.arrival, b.bag_id)))


def make_scene(index: int, split: str) -> Phase2Scene:
    source_group = f"v3_phase2:{split}:{index:03d}"
    def choose(field, lower, upper):
        return indexed_int(610092, source_group, "scenario", field, lower, upper)
    nodes = {
        name: Node(name, "domestic" if name in {"A", "S", "J", "C"} else "international",
                   f"control:{partition}", capacity=8)
        for name, partition in (("A", 0), ("S", 0), ("J", 1), ("C", 1), ("K", 2), ("L", 2), ("B", 3))
    }
    edges = [Edge("stem", "A", "S", 2),
             Edge("S-J", "S", "J", choose("SJ", 1, 3)),
             Edge("J-B", "J", "B", choose("JB", 4, 8)),
             Edge("S-K", "S", "K", choose("SK", 3, 5)),
             Edge("K-B", "K", "B", choose("KB", 4, 8)),
             Edge("S-L", "S", "L", choose("SL", 5, 7)),
             Edge("L-B", "L", "B", choose("LB", 5, 9)),
             Edge("S-B", "S", "B", choose("SB", 16, 22)),
             Edge("C-J", "C", "J", 1),
             Edge("B-A", "B", "A", choose("BA", 7, 11)),
             Edge("old-long", "A", "B", 40)]
    # Replannable target uses soft tardiness. Hard-protected requests retain
    # their full authorized itinerary in the current conservative runtime.
    target = Bag("bag:target", "A", "B", 0, 36, protected=False)
    trays = {"tray:target": Tray("tray:target", "A", "loaded", target.bag_id),
             "tray:C": Tray("tray:C", "C"),
             "tray:old": Tray("tray:old", None, "in_transit")}
    for number in range(choose("Bstock", 0, 2)):
        tray_id = f"tray:B:{number}"
        trays[tray_id] = Tray(tray_id, "B")
    old_at = choose("old_arrival", 8, 26)
    initial = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays,
                       {target.bag_id: target}, old_in_transit=(InFlight("tray:old", "old-long", old_at - 40, old_at),),
                       module=FixedLocalModule(unload_ticks=choose("unload", 1, 2),
                                               hold_by_node={"B": choose("hold", 0, 5)}, reception_capacity=2),
                       load_times={target.bag_id: 0})
    demand_at = choose("B_at", 12, 23)
    competitor_at = choose("C_at", 6, 9)
    forecasts = [RoutingDemandForecast("forecast:B", "B", "A", demand_at,
                                      demand_at + choose("Bwindow", 10, 18), count=choose("Bcount", 1, 3))]
    if choose("competition", 0, 2) > 0:
        forecasts.append(RoutingDemandForecast("forecast:C", "C", "B", competitor_at,
                                               competitor_at + choose("Cwindow", 5, 10), count=1))
    return Phase2Scene(source_group, split, initial, tuple(forecasts),
                       truth_shift=8 if choose("reversal", 0, 4) == 0 else 0)


def phase2_scenes(train=80, validation=20, test=40, deployment=40, evaluation_namespace="") -> tuple[Phase2Scene, ...]:
    result = []
    for split, count in (("train", train), ("validation", validation), ("test", test), ("deployment", deployment)):
        for index in range(count):
            source_split = f"{split}_{evaluation_namespace}" if evaluation_namespace and split in {"test", "deployment"} else split
            result.append(replace(make_scene(index, source_split), split=split))
    return tuple(result)
