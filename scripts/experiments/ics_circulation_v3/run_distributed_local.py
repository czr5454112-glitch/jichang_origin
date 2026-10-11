"""Fixed local-service ablation and negative mechanisms, not held-out evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil

from .distributed_clock import TransportFault, digest
from .distributed_local import LocalDispatchClock, LocalDispatchController
from .distributed_slow import PublishedDemand
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .run_distributed_slow import source_paths as frozen_source_paths


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w2_local_service_20261009"


def _state(a_stock=4, b_stock=2, *, reachable=True):
    nodes = {"A": Node("A", "source", "west", 7), "A2": Node("A2", "source", "west", 7),
             "B": Node("B", "remote", "east", 7)}
    edges = [Edge("A2B", "A2", "B", 3), Edge("AB", "A", "B", 3), Edge("BA", "B", "A", 3)]
    if reachable:
        edges.append(Edge("AA2", "A", "A2", 3))
    trays = {f"A{i}": Tray(f"A{i}", "A") for i in range(a_stock)}
    trays.update({f"B{i}": Tray(f"B{i}", "B") for i in range(b_stock)})
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays, {},
                    module=FixedLocalModule(1, {"A": 1, "A2": 2, "B": 2}, reception_capacity=2))


def _bags(schedule):
    return tuple(Bag(f"b{i}", origin, destination, at, at + 35)
                 for i, (origin, destination, at) in enumerate(schedule))


def _publications(bags):
    return tuple(PublishedDemand(b.bag_id, b.origin, b.arrival, max(0, b.arrival - 18), b.arrival + 60)
                 for b in bags)


def fixtures():
    sustained = _bags((("A2", "B", 0), ("B", "A", 12), ("A2", "B", 22),
                       ("B", "A", 36), ("A2", "B", 54), ("A", "B", 70)))
    mixed = _bags((("A2", "B", 5), ("B", "A", 10), ("B", "A", 24),
                   ("A2", "B", 30), ("A", "B", 48), ("A2", "B", 66)))
    source = _bags((("A", "B", 8), ("A2", "B", 15)))
    queued = _bags((("A2", "B", 0),))
    return (
        {"case_id": "sustained_local_and_cross_owner", "kind": "mixed_continuous", "state": _state(),
         "bags": sustained, "publications": _publications(sustained), "faults": (), "horizon": 125,
         "switches": (False, True), "description": "Six actual tasks alternate local A2 supply and cross-owner loaded traffic."},
        {"case_id": "mixed_reversal_and_lost_ack", "kind": "mixed_continuous", "state": _state(3, 1),
         "bags": mixed, "publications": _publications(mixed) + (
             PublishedDemand("cancelled_local", "A2", 50, 32, 100),
             PublishedDemand("cancelled_local", "A2", 50, 40, 100, revision=2, cancelled=True)),
         "faults": (TransportFault("ACK", drop=True),
                    TransportFault("OWNER_STATUS", destination="west", delay=4)),
         "horizon": 140, "switches": (False, True),
         "description": "Finite reusable trays, reversal after publication and lost acknowledgments; all traffic shares capacity-one edges."},
        {"case_id": "earlier_source_need_blocks_local_move", "kind": "regression", "state": _state(1, 0),
         "bags": source, "publications": _publications(source), "faults": (), "horizon": 20,
         "switches": (True,), "description": "Both tasks have arrived; a later local target must not steal the early source tray; unfinished work is retained."},
        {"case_id": "unreachable_local_queue", "kind": "regression", "state": _state(1, 0, reachable=False),
         "bags": queued, "publications": (), "faults": (), "horizon": 30, "switches": (True,),
         "description": "Actual local queue remains in the bag denominator; no directed path, so no protocol request is issued."},
        {"case_id": "local_lost_ack", "kind": "regression", "state": _state(1, 0), "bags": queued,
         "publications": (), "faults": (TransportFault("ACK", drop=True),), "horizon": 45,
         "switches": (True,), "description": "One real local empty service plus loaded continuation; lost ACK resolved without a second physical action."},
    )


def source_paths():
    paths = frozen_source_paths() + [Path(__file__), Path(__file__).with_name("distributed_local.py"),
                                   ROOT / "tests/test_ics_circulation_v3_distributed_local.py"]
    return tuple(dict.fromkeys(paths))


def hashes():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in source_paths()}


def execute(fixture, enabled):
    controllers = {owner: LocalDispatchController(owner, local_dispatch=enabled, mode="both", period=1,
                                                  departure_lead=4, status_max_age=10)
                   for owner in ("west", "east")}
    world = LocalDispatchClock(fixture["state"], fixture["bags"], local_dispatch=enabled,
        controllers=controllers, publications=fixture["publications"], faults=fixture["faults"],
        message_delay=1, prepare_ttl=12, status_period=1)
    world.advance(min(11, fixture["horizon"] // 2))
    checkpoint = world.checkpoint()
    result = world.advance(fixture["horizon"])
    replay = LocalDispatchClock.from_checkpoint(checkpoint)
    assert replay.local_dispatch is enabled
    assert replay.advance(fixture["horizon"]) == result
    assert {o: p.local_service_audit for o, p in replay.participants.items()} == {
        o: p.local_service_audit for o, p in world.participants.items()}
    return world, result


def run(output):
    if output.exists():
        raise ValueError("output already exists; preserve evidence and choose a fresh directory")
    output.mkdir(parents=True)
    (output / "raw").mkdir()
    initial_hashes = hashes()
    rows, inputs = [], []
    for fixture in fixtures():
        data = {k: v for k, v in fixture.items() if k not in {"state", "bags", "publications", "faults"}}
        data.update(state=asdict(fixture["state"]), bags=[asdict(b) for b in fixture["bags"]],
                    publications=[asdict(p) for p in fixture["publications"]], faults=[asdict(f) for f in fixture["faults"]])
        data["input_sha256"] = digest(data)
        inputs.append(data)
        for enabled in fixture["switches"]:
            world, result = execute(fixture, enabled)
            physical, requests = result.physical, result.requests
            empty = [r for r in requests.values() if r.request.intent == "empty_transfer"]
            local = [r for r in empty if fixture["state"].network.nodes[r.request.destination_node].control_partition == r.request.coordinator]
            committed = [e for e in result.trace if e["event"] == "physical_commit"]
            guards = [e for p in world.participants.values() for e in p.local_service_audit]
            probes = [e for c in world.controllers.values() for e in c.trace if e["event"] == "local_service_probe"]
            row = {"case_id": fixture["case_id"], "kind": fixture["kind"], "mode": "both", "local_dispatch": enabled,
                   "input_sha256": data["input_sha256"], "bag_ids": sorted(b.bag_id for b in fixture["bags"]),
                   "bag_count": len(fixture["bags"]), "completed_count": len(physical.completed), "completed": physical.completed,
                   "on_time_count": sum(t <= physical.final_snapshot.bags[b].deadline for b, t in physical.completed.items()),
                   "uncompleted_ids": physical.uncompleted_bag_ids, "request_count": len(requests),
                   "outcome_counts": result.outcome_counts, "pending_requests": sum(r.outcome is None for r in requests.values()),
                   "owner_commit_count": sum(r.owner_committed for r in requests.values()),
                   "empty_request_count": len(empty), "empty_commit_count": sum(r.owner_committed for r in empty),
                   "local_empty_request_count": len(local), "local_empty_commit_count": sum(r.owner_committed for r in local),
                   "cross_owner_empty_commit_count": sum(r.owner_committed for r in empty if r not in local),
                   "total_cost": physical.total_cost, "components": physical.cost_components,
                   "checkpoint_exact_replay": True, "invariant_checks": physical.invariant_checks,
                   "local_guard_count": len(guards), "local_guard_rejections": dict(Counter(e["reason"] for e in guards if not e["accepted"])),
                   "local_probe_count": len(probes), "local_probe_rejections": dict(Counter(e["reason"] for e in probes if not e["accepted"]))}
            assert set(physical.final_snapshot.bags) == set(row["bag_ids"])
            assert len(physical.final_trays) == len(fixture["state"].trays)
            assert row["completed_count"] + len(row["uncompleted_ids"]) == row["bag_count"]
            assert sum(result.outcome_counts.values()) == row["request_count"]
            assert len(committed) == row["owner_commit_count"]
            assert all(p["other_after"] >= p["other_before"] for e in guards if e["accepted"] for p in e.get("prefixes", ()))
            rows.append(row)
            raw = {"case_id": fixture["case_id"], "local_dispatch": enabled, "input_sha256": data["input_sha256"],
                   "result": asdict(result), "controllers": {o: c.trace for o, c in world.controllers.items()},
                   "source_owner_local_guard": {o: p.local_service_audit for o, p in world.participants.items()}}
            name = fixture["case_id"] + ("__local_on.json" if enabled else "__local_off.json")
            (output / "raw" / name).write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    assert hashes() == initial_hashes, "dependency sources changed during fixture runs"
    totals = {}
    for enabled in (False, True):
        selected = [row for row in rows if row["kind"] == "mixed_continuous" and row["local_dispatch"] is enabled]
        totals["local_on" if enabled else "local_off"] = {k: sum(row[k] for row in selected) for k in (
            "bag_count", "completed_count", "on_time_count", "request_count", "owner_commit_count", "empty_commit_count",
            "local_empty_commit_count", "cross_owner_empty_commit_count", "total_cost")}
    summary = {"experiment": "Opt-in same-owner different-node empty service on the shared physical/message clock",
        "run_count": len(rows), "fixture_count": len(inputs), "mixed_continuous_runs": 4, "regression_runs": 3,
        "same_input_hash_per_local_switch_pair": True, "all_checkpoints_exact": True, "mixed_aggregates": totals,
        "source_sha256": initial_hashes, "limitations": [
            "Two constructed development fixtures reused for the local off/on comparison, plus three mechanism regressions; no held-out claim or strategy fitting.",
            "Both switches use mode=both, period1, identical publications, message faults and external bag tape; only local service capability changes.",
            "Reactive/both may serve any observed actual local queue; predictive only serves published identities and their observed real continuation, exactly as the frozen remote controller does.",
            "Local target credit exists only in admission arithmetic at or after the validated usable tick. It is never firm inventory or a fabricated Bag.",
            "Every other same-zone prefix separately preserves directed unit matching after donor removal; target credit cannot cancel another unit's loss, even at the same tick.",
            "This is a conservative donor filter, not a congestion-aware service-time guarantee for other demands; it may reject feasible sequential reuse and starve undersupplied simultaneous demands.",
            "Source owners repeat checks at prepare and authorize using delivered information only; the earlier frozen distributed protocol and physical arbiter are unchanged.",
            "Same-owner cross-zone movement retains frozen export floor/source protection. Every crossed resource owner must lease its local capacity; global arbiter performs final atomic physical validation.",
            "Fixed FIFO loading can consume a delivered tray for another earlier real queue unit; named forecast claims do not override FIFO.",
            "Path search remains bounded and incomplete; probe failures issue no request but actual unserved bags remain in the task denominator. All submitted requests including pending/unknown are recorded.",
            "Synthetic integer message delays and centralized final physical arbitration, not deployed networking or measured latency.",
            "Prior 23-request and 16-run W2 artifacts and their source snapshots remain unchanged; this capability extension does not establish complete W2 or airport integration."]}
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
    result = run(args.output)
    print(json.dumps({"run_count": result["run_count"], "mixed_aggregates": result["mixed_aggregates"]}, indent=2))
