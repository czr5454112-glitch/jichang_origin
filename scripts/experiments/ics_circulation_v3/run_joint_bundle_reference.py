"""Atomic permission and source-protection development diagnostics."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory
from .joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
from .joint_transactions import commit_joint_actions
from .learning import RoutingDemandForecast
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .runtime import Simulation


SOURCES = ("run_joint_bundle_reference.py", "joint_bundle_reference.py", "joint_reference.py", "joint_transactions.py",
           "model.py", "runtime.py", "routing.py", "learning.py", "evaluation.py", "prebalance.py", "experiment_protocol.py", "dependency_admission.py")


def swap_fixture(size=2):
    nodes = tuple(chr(ord("A") + i) for i in range(size))
    edges = {a + b: Edge(a + b, a, b, 1) for a, b in zip(nodes, nodes[1:] + nodes[:1])}
    bags = {"b" + a: Bag("b" + a, a, b, 0, 5) for a, b in zip(nodes, nodes[1:] + nodes[:1])}
    return Snapshot(0, Network({n: Node(n, n, n, capacity=1) for n in nodes}, edges),
                    {a: Tray(a, a, "loaded", "b" + a) for a in nodes}, bags,
                    module=FixedLocalModule(unload_ticks=0))


def source_reuse_fixture():
    """One export can serve B and physically return before A's known demand.

    A first-known-supply prefix screen cannot credit that uncommitted reuse.
    The different answer demonstrates a protection-domain effect, not a search
    improvement over a comparator that uses the more conservative contract.
    """
    initial = Snapshot(0, Network({n: Node(n, n, n, capacity=2) for n in "AB"},
        {"AB": Edge("AB", "A", "B", 1), "BA": Edge("BA", "B", "A", 1)}),
        {"tray": Tray("tray", "A")}, {}, module=FixedLocalModule(unload_ticks=0))
    forecasts = (RoutingDemandForecast("away", "B", "A", 1, 8),
                 RoutingDemandForecast("home", "A", "B", 3, 8))
    future = tuple(Bag(f.forecast_id + ":0", f.node, f.destination, f.at, f.deadline) for f in forecasts)
    return initial, forecasts, future


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run(output):
    output = create_output_directory(output)
    root = Path(__file__).parent
    source = {name: (root / name).read_bytes() for name in SOURCES}
    hashes = {name: sha256(value).hexdigest() for name, value in source.items()}
    (output / "source_snapshot").mkdir()
    for name, data in source.items():
        (output / "source_snapshot" / name).write_bytes(data)
    save(output / "protocol.json", {"source_sha256": hashes, "development_only": True,
        "planned_calls": 7, "permission_ablation": "2/3 capacity-one cycles, same solver atomic_bundles false/true",
        "source_guard_ablation": "same one-tray near-source-demand fixture, module_only vs shared_forecast_prefix",
        "explicit_failure": "work budget 20, no fabricated lower bound/gap",
        "certificate_scope": "whole_route declared finite positive-walk/integer-time domain, maximum one new commitment per tray per tick; only domain actions are certified",
        "source_guard_atomic_extension": "same single-donor greedy predicate, other same-bundle exporters removed from known supply, new inflows/reuse not credited"})
    cases = []
    for size in (2, 3):
        for atomic in (False, True):
            cases.append((f"capacity_one_cycle_{size}_atomic_{atomic}", swap_fixture(size), (), (),
                          AtomicJointDomain(1, expansion_limit=100000, atomic_bundles=atomic)))
    initial, forecasts, future = source_reuse_fixture()
    for contract in ("module_only", "shared_forecast_prefix"):
        cases.append(("source_reuse_" + contract, initial, forecasts, future,
                      AtomicJointDomain(5, expansion_limit=200000, source_protection_contract=contract)))
    cases.append(("explicit_budget_failure", initial, forecasts, future, AtomicJointDomain(5, expansion_limit=20)))
    metrics = []
    for name, initial, forecasts, future, domain in cases:
        start, cpu = perf_counter(), process_time()
        result = solve_atomic_joint(initial, future, domain=domain, published_forecasts=forecasts)
        replay = Simulation(initial, future, control_mode="external", route_mode="whole_route")
        for tick in range(domain.horizon):
            for bundle in result.schedule:
                if bundle.tick == tick:
                    accepted = commit_joint_actions(replay, bundle.proposals(replay.observe()))
                    if not accepted.accepted:
                        raise AssertionError("Independent incumbent replay failed: " + accepted.reason)
            replay.advance(tick + 1)
        physical = replay.result()
        if result.total_cost is not None and abs(physical.total_cost - result.total_cost) > 1e-10:
            raise AssertionError("Incumbent cost differs from physical replay")
        row = {"name": name, "status": result.status, "complete": result.complete, "cost": result.total_cost,
               "lower_bound": result.lower_bound, "gap": result.gap, "work_used": result.diagnostics["work_used"],
               "scheduled_bags": len(initial.bags) + len(future), "completed": len(physical.completed),
               "source_protection_contract": domain.source_protection_contract, "atomic_bundles": domain.atomic_bundles,
               "wall_seconds": perf_counter() - start, "process_cpu_seconds": process_time() - cpu}
        metrics.append(row)
        save(output / (name + ".json"), {"metrics": row, "initial": asdict(initial),
            "published_forecasts": [asdict(f) for f in forecasts], "future_tape_offline_oracle_only": [asdict(b) for b in future],
            "search": asdict(result), "independent_replay": asdict(physical)})
        print(json.dumps(row), flush=True)
    summary = {"source_sha256": hashes, "metrics": metrics, "calls": len(metrics),
               "source_changed_during_run": any((root / name).read_bytes() != data for name, data in source.items()),
               "scope": "development mechanism diagnostics; no online future-truth optimum claim; source-contract differences are not pure search gains"}
    save(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.output)
    raise SystemExit(int(result["source_changed_during_run"]))
