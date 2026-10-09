"""Predeclared small circulating, finite-buffer mechanism fixtures (W2 start)."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .learning import RoutingDemandForecast
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .phase4_control import ControlSpec, build_engine


@dataclass(frozen=True)
class CouplingScene:
    name: str
    initial: Snapshot
    forecasts: tuple
    future_bags: tuple  # Runner/event engine only; never passed to policy callbacks.
    horizon: int
    provenance: dict


def coupling_scene(kind="scarce"):
    if kind not in {"scarce", "sufficient", "reversal"}:
        raise ValueError("unknown predeclared mechanism fixture")
    nodes = {name: Node(name, "zone_A" if name in {"A", "J", "C"} else "zone_B", name,
                       capacity=2 if name in {"A", "B"} else 1, can_wait=name not in {"J", "K"})
             for name in ("A", "J", "B", "K", "C")}
    edges = (Edge("A-J", "A", "J", 1), Edge("J-B", "J", "B", 4),
             Edge("B-K", "B", "K", 1), Edge("K-A", "K", "A", 4),
             Edge("C-A", "C", "A", 1), Edge("A-C", "A", "C", 1))
    warm = Bag("warm", "A", "B", 0, 8, protected=True)
    trays = {"warm_tray": Tray("warm_tray", "A", "loaded", "warm"),
             "B_stock": Tray("B_stock", "B"), "C_pool": Tray("C_pool", "C")}
    if kind == "sufficient":
        trays["B_spare"] = Tray("B_spare", "B")
    initial = Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}), trays, {"warm": warm},
                       module=FixedLocalModule(unload_ticks=1, export_min_stock=0, reception_capacity=1))
    forecasts, truth = [], []
    # Initial published demand contains the B burst. Later A/B arrivals are
    # published at their own rolling release times, not exposed as early truth.
    for origin, at, publication in (("B", 2, 0), ("B", 8, 0), ("B", 10, 0),
                                    ("A", 12, 12), ("A", 22, 20), ("B", 24, 20), ("B", 30, 26)):
        forecast_id = f"stream:{origin}:{at}"
        destination = "A" if origin == "B" else "B"
        forecasts.append(RoutingDemandForecast(forecast_id, origin, destination, at, at + 16, published_at=publication))
        actual_origin = "A" if kind == "reversal" and at == 10 else origin
        actual_destination = "B" if actual_origin == "A" else "A"
        truth.append(Bag(f"{forecast_id}:0", actual_origin, actual_destination, at, at + 16))
        if kind == "reversal" and at == 10:
            forecasts.append(replace(forecasts[-1], count=0, published_at=7))
    # A real authorized burn-in leaves the warm protected load on the long
    # connection; no hand-authored unowned edge reservations are injected.
    burned = build_engine(initial, (), (), ControlSpec(routing="baseline", predictive=False)).advance(1)
    return CouplingScene(kind, burned.final_snapshot, tuple(forecasts), tuple(truth), 44,
                         {"source": "declared_synthetic_five_node_recirculating_mechanism_not_airport_data",
                          "burn_in": {"ticks": 1, "trace": list(burned.trace), "invariant_checks": burned.invariant_checks},
                          "finite_initial_trays": len(trays), "node_capacities": {name: node.capacity for name, node in nodes.items()},
                          "no_wait_nodes": ["J", "K"], "long_edges_ticks": {"J-B": 4, "K-A": 4},
                          "rolling_forecast_publication_is_proxy": True,
                          "reversal": "B@10 forecast cancelled at7 after planned departure; observed actual origin A@10" if kind == "reversal" else None,
                          "claim": "mechanism_fixture_not_heldout_performance_sample"})


def coupling_scenes():
    return tuple(coupling_scene(kind) for kind in ("scarce", "sufficient", "reversal"))
