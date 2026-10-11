"""Matched continuous fast/slow W2 scenarios; all inputs are development fixtures."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil

from .distributed_clock import DistributedClock, TransportFault, digest
from .distributed_slow import LocalClockController, PublishedDemand
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .run_distributed_clock import source_paths as clock_source_paths


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w2_slow_20261009"
MODES = ("none", "reactive", "predictive", "both")


def _snapshot(a_stock, b_stock=0):
    nodes = {n: Node(n, n, "west" if n == "A" else "east", capacity=7) for n in ("A", "B")}
    edges = (Edge("AB", "A", "B", 8), Edge("BA", "B", "A", 8))
    trays = {f"A{i}": Tray(f"A{i}", "A") for i in range(a_stock)}
    trays.update({f"B{i}": Tray(f"B{i}", "B") for i in range(b_stock)})
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays, {},
                    module=FixedLocalModule(1, {"A": 1, "B": 3}, reception_capacity=2))


def _bags(schedule):
    return tuple(Bag(f"b{i}", node, "B" if node == "A" else "A", tick, tick + 35)
                 for i, (node, tick) in enumerate(schedule))


def _published(bags):
    return tuple(PublishedDemand(bag.bag_id, bag.origin, bag.arrival,
                                 max(0, bag.arrival - 20), bag.arrival + 50) for bag in bags)


def fixtures():
    steady = _bags((("A", 0), ("B", 12), ("B", 20), ("A", 32), ("B", 45), ("A", 62)))
    scarce = _bags((("A", 18), ("B", 35), ("A", 65)))
    reverse = _bags((("B", 25), ("A", 50)))
    counterflow = _bags((("A", 0), ("B", 0), ("B", 10), ("B", 18), ("A", 28),
                        ("A", 45), ("B", 58), ("A", 75), ("A", 85)))
    return (
        {"case_id": "sustained_six_bags", "snapshot": _snapshot(4), "bags": steady,
         "publications": _published(steady), "horizon": 115, "message_delay": 1, "departure_lead": 4,
         "faults": (TransportFault("ACK", drop=True),), "description": "Repeated arrivals; lost acknowledgment; finite reusable stock."},
        {"case_id": "overdue_source_guard", "snapshot": _snapshot(1), "bags": scarce,
         "publications": (PublishedDemand("b0", "A", 6, 0, 55), PublishedDemand("b1", "B", 12, 0, 85),
                          PublishedDemand("b2", "A", 65, 45, 110)),
         "horizon": 125, "message_delay": 1, "departure_lead": 4, "faults": (),
         "description": "One tray; known source demand arrives after nominal forecast; source protection remains active."},
        {"case_id": "forecast_reversal_before_and_after_commit", "snapshot": _snapshot(3), "bags": reverse,
         "publications": _published(reverse) + (
             PublishedDemand("ghost_before", "B", 12, 0, 70),
             PublishedDemand("ghost_before", "B", 12, 5, 70, revision=2, cancelled=True),
             PublishedDemand("ghost_after", "B", 35, 12, 80),
             PublishedDemand("ghost_after", "B", 35, 25, 80, revision=2, cancelled=True)),
         "horizon": 110, "message_delay": 1, "departure_lead": 4, "faults": (),
         "description": "One predicted demand reverses before admission, another after irrevocable transfer admission."},
        {"case_id": "counterflow_delayed_status", "snapshot": _snapshot(3, 1), "bags": counterflow,
         "publications": _published(counterflow), "horizon": 150, "message_delay": 2, "departure_lead": 8,
         "faults": (TransportFault("OWNER_STATUS", destination="west", delay=9),
                    TransportFault("DEMAND_FORECAST", destination="east", delay=8)),
         "description": "Loaded/empty traffic uses the same capacity-one directed edges; delayed/reordered information."},
    )


def source_paths():
    return clock_source_paths() + [Path(__file__), Path(__file__).with_name("distributed_slow.py"),
                                  ROOT / "tests/test_ics_circulation_v3_distributed_slow.py"]


def hashes():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in source_paths()}


def run(output):
    if output.exists():
        raise ValueError("output exists; preserve it and choose a new directory")
    output.mkdir(parents=True)
    source_hashes = hashes()
    inputs, rows = [], []
    (output / "raw").mkdir()
    for fixture in fixtures():
        input_data = {key: value for key, value in fixture.items() if key not in {"snapshot", "bags", "publications", "faults"}}
        input_data.update(snapshot=asdict(fixture["snapshot"]), bags=[asdict(b) for b in fixture["bags"]],
                          publications=[asdict(p) for p in fixture["publications"]], faults=[asdict(f) for f in fixture["faults"]])
        input_data["input_sha256"] = digest(input_data)
        inputs.append(input_data)
        for mode in MODES:
            controllers = {owner: LocalClockController(owner, mode=mode, period=3,
                            departure_lead=fixture["departure_lead"], status_max_age=10)
                           for owner in ("west", "east")}
            world = DistributedClock(fixture["snapshot"], fixture["bags"],
                    controllers=controllers, publications=fixture["publications"],
                    faults=fixture["faults"], message_delay=fixture["message_delay"], prepare_ttl=12)
            world.advance(27)
            checkpoint = world.checkpoint()
            result = world.advance(fixture["horizon"])
            assert DistributedClock.from_checkpoint(checkpoint).advance(fixture["horizon"]) == result
            physical = result.physical
            empty = [record for record in result.requests.values() if record.request.intent == "empty_transfer"]
            commits = [event for event in result.trace if event["event"] == "physical_commit"]
            row = {"case_id": fixture["case_id"], "mode": mode, "input_sha256": input_data["input_sha256"],
                   "bag_ids": sorted(b.bag_id for b in fixture["bags"]), "bag_count": len(fixture["bags"]),
                   "completed_count": len(physical.completed), "completed": physical.completed,
                   "on_time_count": sum(t <= physical.final_snapshot.bags[b].deadline for b, t in physical.completed.items()),
                   "uncompleted_ids": physical.uncompleted_bag_ids, "request_count": len(result.requests),
                   "outcome_counts": result.outcome_counts, "pending_requests": sum(r.outcome is None for r in result.requests.values()),
                   "owner_commit_count": sum(r.owner_committed for r in result.requests.values()),
                   "empty_request_count": len(empty), "empty_commit_count": sum(r.owner_committed for r in empty),
                   "empty_demands_committed": [r.request.demand_id for r in empty if r.owner_committed],
                   "loaded_commit_count": sum(event["candidate"]["bag_id"] is not None for event in commits),
                   "total_cost": physical.total_cost, "components": physical.cost_components,
                   "checkpoint_exact_replay": True, "invariant_checks": physical.invariant_checks,
                   "slow_ticks": sum(e["event"] == "slow_tick" for c in world.controllers.values() for e in c.trace),
                   "forecast_received": sum(e["event"] == "forecast_received" for c in world.controllers.values() for e in c.trace),
                   "protocol_fences": sum(e["event"] == "attempt_fenced" for e in result.trace)}
            assert set(physical.final_snapshot.bags) == set(row["bag_ids"])
            assert len(physical.final_trays) == len(fixture["snapshot"].trays)
            assert sum(result.outcome_counts.values()) == row["request_count"]
            assert row["owner_commit_count"] == len(commits)
            rows.append(row)
            raw = {"case_id": fixture["case_id"], "mode": mode, "input_sha256": input_data["input_sha256"],
                   "result": asdict(result), "controllers": {owner: controller.trace for owner, controller in world.controllers.items()}}
            (output / "raw" / f"{fixture['case_id']}__{mode}.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    assert hashes() == source_hashes, "sources changed during measured scenarios"
    aggregates = {}
    for mode in MODES:
        selected = [row for row in rows if row["mode"] == mode]
        outcomes = Counter()
        for row in selected:
            outcomes.update(row["outcome_counts"])
        aggregates[mode] = {key: sum(row[key] for row in selected) for key in
                           ("bag_count", "completed_count", "on_time_count", "request_count", "empty_request_count",
                            "empty_commit_count", "owner_commit_count", "total_cost")}
        aggregates[mode]["outcome_counts"] = dict(outcomes)
    summary = {"experiment": "Continuous two-owner fast/slow shared-clock development scenarios",
               "run_count": len(rows), "fixture_count": len(inputs), "modes": MODES,
               "same_input_hash_and_all_bag_denominator_per_fixture": True,
               "all_checkpoints_exact": True, "aggregates": aggregates, "source_sha256": source_hashes,
               "limitations": ["Four constructed development fixtures reused across four modes; not unseen generalization.",
                 "Initial stock/capacity differ between fixtures; within each fixture mode inputs are identical.",
                 "Source protection uses the same published demand stream in all transfer modes; none disables all slow actions.",
                 "Source donor guard preserves directed local same-zone unit matching at demand prefixes; this is not a congestion/timing service guarantee.",
                 "Source owners repeat the donor guard at prepare and final lease authorization using only information already delivered to that owner; messages still in flight cannot be used retroactively.",
                 "Predictions are demand only, never fabricated available stock; latest revisions and expiry gate visibility.",
                 "Conflicting content at the same forecast version blocks new slow exports until a higher version; delivered loading identities never expire.",
                 "Initial old transit/completed identities enter origin owners through explicit TASK_STATE messages; unseen ledger bags are not assumed waiting.",
                 "Observed waiting identities supersede prediction location/expiry/cancellation and persist until a delivered loading fact; a prediction cannot delete observed real work.",
                 "Whole-route physical arbiter is centralized and explicitly distinguished from partition-local planning.",
                 "Local source-only waiting search is incomplete; failures and uncompleted bags remain in the denominator.",
                 "Prepared claims suppress duplicate attempts but are not committed supply; accepted empty transfers are irrevocable.",
                 "Named accepted-demand stock cannot be re-exported until FIFO consumes it, the unit is loaded, or delivered cancellation/explicit request TTL releases the claim; fixed FIFO itself is unchanged.",
                 "Synthetic endpoint failures/message clocks; zero simulated CPU duration; no actual network or latency guarantee.",
                 "No learning/fitting/parameter selection; fixed period 3, status period 2 and declared lead by transport setting.",
                 "Remote owner summaries have timestamps but are asynchronous, so forecasting can produce unnecessary transfers."]}
    for name, value in (("inputs.json", inputs), ("rows.json", rows), ("summary.json", summary)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    for source in source_paths():
        target = output / "source_snapshot" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    manifest = {str(p.relative_to(output)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = run(args.output)
    print(json.dumps({"run_count": summary["run_count"], "aggregates": summary["aggregates"]}, indent=2))
