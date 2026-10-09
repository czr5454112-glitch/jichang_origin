"""Controlled request-denominator audit, with synthetic transport accounting."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from statistics import mean

from .model import Bag, Edge, Network, Node, Snapshot, Tray
from .request_service import (AttemptFault, OUTCOMES, ResourceOwner, RouteRequest,
                              RoutingRequestService, TransportScript, digest)
from .routing import RegionalCandidateGenerator
from .runtime import Simulation


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "outputs/experiments/ics_circulation_v3/phase3_request_service_20261009"


def snapshot_fixture():
    nodes = {name: Node(name, name, f"control:{name}", 4) for name in ("A", "J", "K", "B")}
    edges = (Edge("A-J", "A", "J", 2), Edge("J-B", "J", "B", 3),
             Edge("A-K", "A", "K", 3), Edge("K-B", "K", "B", 3))
    bag = Bag("bag", "A", "B", 0, 20)
    return Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}),
                    {"tray": Tray("tray", "A", "loaded", "bag")}, {"bag": bag})


@dataclass(frozen=True)
class ControlledCase:
    name: str
    expected_outcome: str
    state: Snapshot
    transport: TransportScript = TransportScript()
    max_attempts: int = 2
    generator_variant: str = "regular"
    policy_variant: str = "regular"


def cases():
    base = snapshot_fixture()
    engine = Simulation(base, route_mode="whole_route")
    full = engine.advance(1).final_snapshot
    prefix = Simulation(base, route_mode="next_edge").advance(1).final_snapshot
    invalid_old = full.clone()
    invalid_old.reservations = tuple(slot for slot in invalid_old.reservations if slot.resource != "edge:J-B")
    unreachable = base.clone()
    unreachable.network = replace(unreachable.network, edges={key: edge for key, edge in unreachable.network.edges.items() if edge.target != "B"})
    def script(**kwargs):
        return TransportScript((AttemptFault(**kwargs),), repeat_last=True)
    return (
        ControlledCase("fresh_request", "new_route_success", base),
        ControlledCase("valid_entered_full_old_route", "still_valid_old_route", full),
        ControlledCase("entered_prefix_is_not_full_fallback", "commit_failure", prefix),
        ControlledCase("old_full_missing_future_reservation", "commit_failure", invalid_old),
        ControlledCase("bounded_search_exhaustion", "search_exhausted", base, generator_variant="expansion_one"),
        ControlledCase("horizon_exhaustion_not_infeasible", "search_exhausted", base, generator_variant="horizon_zero"),
        ControlledCase("static_no_path_proof", "proven_infeasible", unreachable),
        ControlledCase("snapshot_communication_failure", "communication_failure", base, script(fail_snapshot=True)),
        ControlledCase("invalid_partition_summary", "communication_failure", base, script(invalid_summary=True)),
        ControlledCase("stale_summary_refresh_succeeds", "new_route_success", base,
                       TransportScript((AttemptFault(stale_summary_before_delivery=True),))),
        ControlledCase("stale_commit_exhausts_retry", "commit_failure", base, script(invalidate_before_commit=True), max_attempts=3),
        ControlledCase("commit_message_failure", "communication_failure", base, script(fail_commit_message=True)),
        ControlledCase("lost_ack_recovered_idempotently", "new_route_success", base,
                       TransportScript((AttemptFault(lose_acknowledgement=True),))),
        ControlledCase("lost_ack_unknown_to_client", "communication_failure", base,
                       script(lose_acknowledgement=True), max_attempts=1),
        ControlledCase("scorer_selects_unauthorized_action", "commit_failure", base, policy_variant="unauthorized"),
        ControlledCase("broken_local_scorer", "local_processing_failure", base, policy_variant="exception"),
        ControlledCase("synthetic_delay_exceeds_100ms", "new_route_success", base,
                       script(queue_ms=70, snapshot_message_ms=40, commit_message_ms=20, acknowledgement_ms=10)),
    )


def service_for(owner, case):
    kwargs = {}
    if case.generator_variant == "expansion_one":
        kwargs["generator_factory"] = lambda: RegionalCandidateGenerator(expansion_limit=1, deadline_ms=None)
    elif case.generator_variant == "horizon_zero":
        kwargs["generator_factory"] = lambda: RegionalCandidateGenerator(horizon=0, deadline_ms=None)
    if case.policy_variant == "unauthorized":
        kwargs["selector"] = lambda snapshot, candidates, features: replace(candidates[0], usable_at=candidates[0].usable_at + 99)
    elif case.policy_variant == "exception":
        def broken(*args):
            raise RuntimeError("injected local scorer failure")
        kwargs["selector"] = broken
    return RoutingRequestService(owner, **kwargs)


def sources():
    directory = Path(__file__).resolve().parent
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("request_service.py", "run_request_service.py", "runtime.py", "model.py", "routing.py")}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(output=DEFAULT_OUTPUT, *, repeats=3):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    output.mkdir(parents=True, exist_ok=True)
    before = sources()
    records = []
    for repeat in range(repeats):
        for case in cases():
            request = RouteRequest(f"{case.name}:{repeat}", "bag", "tray", max_attempts=case.max_attempts)
            owner = ResourceOwner(case.state)
            result = service_for(owner, case).handle(request, case.transport)
            after = owner.snapshot()
            record = {"case": case.name, "repeat": repeat, "expected_outcome": case.expected_outcome,
                      "classification_matches_fixture": result.status == case.expected_outcome,
                      "input_sha256": digest({"state": asdict(case.state), "request": asdict(request),
                                              "transport": asdict(case.transport), "generator": case.generator_variant,
                                              "policy": case.policy_variant}),
                      "initial": asdict(case.state), "request": asdict(request), "transport_script": asdict(case.transport),
                      "result": asdict(result), "final_owner_state": asdict(after),
                      "finite_tray_ids_preserved": set(after.trays) == set(case.state.trays),
                      "all_bag_ids_preserved": set(after.bags) == set(case.state.bags),
                      "real_local_over_100ms": result.timings["local_wall_ms"] > 100,
                      "accounted_with_synthetic_transport_over_100ms": result.timings["accounted_end_to_end_ms"] > 100}
            records.append(record)
    counts = Counter(record["result"]["status"] for record in records)
    summary = {
        "schema": "czr005.ics_circulation_v3.request_service.v1",
        "scope": "LOCAL_OWNER_WITH_SYNTHETIC_TRANSPORT_ACCOUNTING_NOT_DISTRIBUTED_INTEGRATION",
        "request_count": len(records), "unique_request_count": len({record["request"]["request_id"] for record in records}),
        "controlled_case_count": len(cases()), "repeats": repeats,
        "static_cache_policy": "process cache retained; fixture preparation can warm static topology",
        "outcome_counts": {status: counts[status] for status in OUTCOMES},
        "denominator_reconciles": sum(counts.values()) == len(records),
        "all_expected_classifications_match": all(record["classification_matches_fixture"] for record in records),
        "all_finite_tray_ids_preserved": all(record["finite_tray_ids_preserved"] for record in records),
        "all_bag_ids_preserved": all(record["all_bag_ids_preserved"] for record in records),
        "real_local_over_100ms_count": sum(record["real_local_over_100ms"] for record in records),
        "accounted_with_synthetic_transport_over_100ms_count": sum(record["accounted_with_synthetic_transport_over_100ms"] for record in records),
        "owner_committed_but_unacknowledged_count": sum(record["result"]["owner_committed"] and not record["result"]["acknowledged"] for record in records),
        "mean_measured_local_wall_ms": mean(record["result"]["timings"]["local_wall_ms"] for record in records),
        "mean_accounted_end_to_end_ms": mean(record["result"]["timings"]["accounted_end_to_end_ms"] for record in records),
        "source_sha256": before, "source_changed_during_run": before != sources(),
        "limitations": [
            "Transport durations/faults are deterministic injected accounting, not measurements of any network.",
            "Synthetic delays do not advance the physical snapshot tick; this audit does not establish a real-time controller guarantee.",
            "Complete visible snapshots with dependency digests are used; private regional state and authenticated distributed RPC are not implemented.",
            "Success-path generation, features, scoring, owner revalidation and commit are separately timed with perf_counter.",
            "Successful snapshot receipt also represents an owner-receipt query; it can recover an accepted request after an acknowledgement loss.",
            "owner_committed means this request_id has an accepted new-route receipt; old-route fallback is separately identified.",
            "Full committed old-route fallback checks future owned reservations and physical state; entered prefixes and bare proposals do not qualify.",
            "Only a revalidated complete-graph static no-path certificate yields proven_infeasible; search truncation never does.",
            "The six specified business outcomes plus explicit local_processing_failure retain broken extensions in the denominator.",
            "Controlled fault cases are coverage examples, not an operational failure distribution or airport benchmark.",
        ],
    }
    write(output / "summary.json", summary)
    write(output / "requests.json", records)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    summary = run(args.output, repeats=args.repeats)
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_expected_classifications_match"] and not summary["source_changed_during_run"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
