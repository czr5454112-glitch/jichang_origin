"""Controlled W2 mechanism evidence. Synthetic fixtures, not held-out results."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

from .distributed_clock import (ClockRequest, DistributedClock, LocalRoutePlanner,
                                OwnerOutage, TransportFault, digest)
from .model import Bag, Edge, FixedLocalModule, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from .runtime import ExecutionValidator


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w2_clock_20261009"


def _state(*, long=4, no_wait=False, bags=1, protected=False, old=False, wait=0):
    nodes = {n: Node(n, n, "west" if n == "A" else "east", capacity=4,
                     can_wait=n != "J" or not no_wait) for n in ("A", "J", "V", "B")}
    edges = (Edge("AJ", "A", "J", long), Edge("JB", "J", "B", 2),
             Edge("JV", "J", "V", 2), Edge("VB", "V", "B", 2))
    tasks = {f"b{i}": Bag(f"b{i}", "A", "B", 0, 70, protected) for i in range(bags)}
    state = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                     {f"t{i}": Tray(f"t{i}", "A", "loaded", f"b{i}") for i in range(bags)}, tasks,
                     module=FixedLocalModule(1, {"B": 2}), load_times={bid: 0 for bid in tasks},
                     replaceable_trays=tuple(f"t{i}" for i in range(bags)))
    if old:
        end = long + wait + 3
        candidate = RouteCandidate("old", "b0", "t0",
             (Leg("AJ", 0, long), Leg("JB", long + wait, long + wait + 2)), end, end + 2, 0, "old")
        assert ExecutionValidator().commit(state, candidate).accepted
    return state


def _request(name="r", i=0, **kwargs):
    return ClockRequest(name, "west", f"b{i}", f"t{i}", **kwargs)


def fixtures():
    def case(name, state=None, requests=None, *, horizon=40, **settings):
        return {"case_id": name, "state": state or _state(),
                "requests": requests or (_request(),), "settings": settings, "horizon": horizon}
    blocked = _state()
    blocked.trays["remote_stock"] = Tray("remote_stock", "B")
    blocked.network.nodes["B"] = replace(blocked.network.nodes["B"], capacity=1)
    disconnected = _state()
    disconnected.network.edges.clear()
    return (
        case("normal_two_owner"),
        case("long_edge_delayed_ack", _state(long=8), (_request(timeout_ticks=15),),
             faults=(TransportFault("ACK", delay=8),)),
        case("cross_owner_no_wait", _state(no_wait=True)),
        case("conflicting_requests", _state(bags=2),
             (_request("one", 0, max_attempts=5), _request("two", 1, max_attempts=5))),
        case("remote_private_capacity_conflict", blocked, (_request(max_attempts=2),)),
        case("physical_departure_window_expired", faults=(TransportFault("COMMIT", attempt=1, delay=8),),
             prepare_ttl=20, requests=(_request(timeout_ticks=20),)),
        case("prepare_lease_expired", prepare_ttl=1, requests=(_request(max_attempts=2),)),
        case("lost_ack_recovered", faults=(TransportFault("ACK", drop=True),)),
        case("lost_ack_and_receipt_unknown", faults=(TransportFault("ACK", drop=True),
                                                      TransportFault("RECEIPT", drop=True))),
        case("duplicated_reordered_messages", faults=(TransportFault("OPEN", duplicate_delays=(0, 11)),
              TransportFault("PREPARE", destination="east", duplicate_delays=(0, 8)),
              TransportFault("COMMIT", duplicate_delays=(0, 9)))),
        case("resolve_fences_late_commit", prepare_ttl=30,
             requests=(_request(departure_lead=15, timeout_ticks=10, max_attempts=2),), horizon=50,
             faults=(TransportFault("COMMIT", attempt=1, delay=12),)),
        case("authorized_long_edge_update", _state(long=20, old=True),
             (_request(intent="update_suffix", avoid_edges=("JB",)),)),
        case("no_wait_update_preserves_chain", _state(long=20, no_wait=True, old=True),
             (_request(intent="update_suffix", avoid_edges=("JB",)),)),
        case("update_arrives_after_anchor", _state(long=8, old=True, wait=5),
             (_request(intent="update_suffix", avoid_edges=("JB",), max_attempts=1, timeout_ticks=25),),
             prepare_ttl=30, faults=(TransportFault("COMMIT", delay=11),)),
        case("owner_recovery_update", _state(long=20, old=True),
             (_request(intent="update_suffix", avoid_edges=("JB",), timeout_ticks=9),),
             outages=(OwnerOutage("east", 2, 8),)),
        case("owner_failure_after_votes", _state(long=20, old=True),
             (_request(intent="update_suffix", avoid_edges=("JB",), max_attempts=1),),
             outages=(OwnerOutage("east", 5, 10),)),
        case("permanent_owner_failure", requests=(_request(max_attempts=2, timeout_ticks=6),),
             outages=(OwnerOutage("east", 0, 100),)),
        case("protected_keep_and_rejected_update", _state(long=20, protected=True, old=True),
             (_request("keep", intent="keep_valid"), _request("update", intent="update_suffix", max_attempts=1))),
        case("wrong_coordinator_rejected", _state(long=20, old=True),
             (replace(_request(intent="update_suffix", max_attempts=1), coordinator="east"),)),
        case("static_no_path", disconnected, (_request(max_attempts=1),)),
        case("bounded_search_not_infeasible", requests=(_request(max_attempts=1),),
             planner=LocalRoutePlanner(expansion_limit=1)),
    )


def source_paths():
    folder = Path(__file__).parent
    return [folder / name for name in ("distributed_clock.py", "run_distributed_clock.py", "runtime.py", "model.py",
                                      "partition_observation.py", "request_service.py", "routing.py")] + [
            ROOT / "tests/test_ics_circulation_v3_distributed_clock.py"]


def _hashes():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in source_paths()}


def run(output):
    if output.exists():
        raise ValueError("output exists; use a new directory to preserve evidence")
    output.mkdir(parents=True)
    frozen = _hashes()
    inputs, rows, raw = [], [], []
    for fixture in fixtures():
        settings = dict(fixture["settings"])
        encoded_settings = {key: (value.__dict__ if key == "planner" else
                            [asdict(v) for v in value] if isinstance(value, tuple) else value)
                            for key, value in settings.items()}
        input_row = {"case_id": fixture["case_id"], "snapshot": asdict(fixture["state"]),
                     "requests": [asdict(r) for r in fixture["requests"]], "settings": encoded_settings,
                     "horizon": fixture["horizon"], "future_bags": []}
        input_row["input_sha256"] = digest(input_row)
        inputs.append(input_row)
        world = DistributedClock(fixture["state"], **settings)
        for request in fixture["requests"]:
            world.submit(request)
        world.advance(7)
        restored = DistributedClock.from_checkpoint(world.checkpoint())
        result = world.advance(fixture["horizon"])
        assert restored.advance(fixture["horizon"]) == result
        physical = result.physical
        requests = list(result.requests.values())
        row = {"case_id": fixture["case_id"], "input_sha256": input_row["input_sha256"],
               "request_count": len(requests), "outcome_counts": result.outcome_counts,
               "physical_commit_count": sum(r.owner_committed for r in requests),
               "acknowledged_count": sum(r.acknowledged for r in requests),
               "pending_count": sum(r.outcome is None for r in requests),
               "bag_count": len(physical.final_snapshot.bags), "completed_count": len(physical.completed),
               "on_time_count": sum(t <= physical.final_snapshot.bags[b].deadline for b, t in physical.completed.items()),
               "total_cost": physical.total_cost, "components": physical.cost_components,
               "checkpoint_exact_replay": True, "physical_invariant_checks": physical.invariant_checks,
               "actual_commit_events": sum(e["event"] == "physical_commit" for e in result.trace),
               "attempts": {key: record.attempt for key, record in result.requests.items()}}
        assert sum(row["outcome_counts"].values()) == row["request_count"]
        assert row["physical_commit_count"] == row["actual_commit_events"]
        rows.append(row)
        raw.append({"case_id": fixture["case_id"], "input_sha256": input_row["input_sha256"], "result": asdict(result)})
    assert _hashes() == frozen, "source changed during run"
    counts = {}
    for row in rows:
        for outcome, count in row["outcome_counts"].items():
            counts[outcome] = counts.get(outcome, 0) + count
    summary = {"experiment": "W2 shared physical/message clock", "fixture_count": len(rows),
               "request_count": sum(row["request_count"] for row in rows), "outcome_counts": counts,
               "physical_commit_count": sum(row["physical_commit_count"] for row in rows),
               "all_checkpoint_replays_exact": True, "source_sha256": frozen,
               "limitations": ["Controlled synthetic development fixtures; no held-out generalization claim.",
                 "In-process event loop and data-flow isolation, not deployed distributed services or process security.",
                 "Public topology/module parameters; local static search permits contiguous traversal and initial waiting only.",
                 "Atomic global physical arbiter is an explicit proxy; planners never receive its global calendars.",
                 "Short local prepare leases are not physical commitments or guaranteed future tray supply.",
                 "Owner outage has an explicit synthetic failure-detector message, itself delayable/droppable.",
                 "Integer transport delays advance physical motion; CPU is zero simulated duration; no real network latency claim.",
                 "Unknown outcomes remain unknown at coordinator; owner_committed is offline ground truth only.",
                 "Suffix authority is original task partition plus explicit replaceable_trays; protected/empty obligations remain irrevocable.",
                 "An unresolved request can retain an admission token until a resolve reaches the arbiter; no claim of crash consensus."]}
    for name, value in (("inputs.json", inputs), ("rows.json", rows), ("raw.json", raw), ("summary.json", summary)):
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
    arguments = parser.parse_args()
    summary = run(arguments.output)
    print(json.dumps({key: summary[key] for key in ("fixture_count", "request_count", "outcome_counts", "physical_commit_count")}, indent=2))
