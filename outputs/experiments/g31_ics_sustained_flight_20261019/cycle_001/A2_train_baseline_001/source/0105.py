"""Bounded offline timing-reference challenge to the immutable LT2 reuse study.

Candidate construction uses saved lawful checkpoint observations and public
durations, never branch outcomes. Native forks are reference labels only.
"""
from __future__ import annotations

import argparse
import ast
import copy
import gzip
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback

from . import research_synthetic_reuse_chain as study
from .native_host import load_native
from .original_workload import digest, write_json

MAX_BRANCHES = 96
FIXED_TIMINGS = 31
COMMAND_DELAY = .01


def candidate_plan(data: dict, views: dict) -> dict:
    """Outcome-independent diagnostic boundaries, not exact permission times."""
    public = views["A"]
    if public["now"] != study.START or views["B"]["now"] != study.START:
        raise ValueError("reference:checkpoint_time")
    service = {row[0]: row[2] for row in public["node_records"]}
    travel = {(u, v): length / speed for u, v, length, speed in public["edge_records"]}
    local = next(j for j in public["jobs"] if j["business_bag_id"] == "loaded")
    if local["loaded_at"] < 0:
        raise ValueError("reference:loaded_checkpoint_required")
    committed = max(study.START, local["loaded_at"] + service[0])
    arrival = committed + travel[0, 1]
    clearance = arrival + service[1]
    lead = service[5] + travel[5, 1]
    headway = next(e["entry_headway"] for e in public["edge_contracts"]
                   if e["from"] == 3 and e["to"] == 4)
    centers = [
        ("loaded_nominal_01_commit", committed, "max(checkpoint, local loaded_at + public service0)"),
        ("loaded_nominal_1_arrival", arrival, "nominal01commit + public travel01"),
        ("loaded_nominal_1_clearance", clearance, "nominal1arrival + public service1"),
        ("empty_arrival_aligned_to_01_commit", committed - lead, "nominal01commit - (public service5 + travel51)"),
        ("empty_arrival_aligned_to_1_clearance", clearance - lead, "nominal1clearance - (public service5 + travel51)"),
        ("headway_expanded_clearance_alignment", clearance + headway - lead,
         "nominal1clearance + public shared edge34 headway - (service5 + travel51); heuristic seed"),
    ]
    # This helper reads only public node/edge durations, not data['jobs'].
    old = list(study.departure_windows(data))
    lower, upper = min(old), max(old)
    epsilon = study.PERIOD / 50
    origins: dict[float, list[str]] = {}
    for i, value in enumerate(old):
        origins.setdefault(value, []).append(f"old_window{i}")
    for name, center, _ in centers:
        for offset, label in [(-epsilon, "before"), (0., "equal"), (epsilon, "after")]:
            value = center + offset
            if lower <= value <= upper:
                origins.setdefault(value, []).append(f"{name}:{label}")
    seeds = sorted(origins)
    if len(seeds) > FIXED_TIMINGS:
        raise ValueError("reference:seed_budget_exceeded")
    refinements = []
    # Repeated longest-interval bisection, deterministic tie break by left edge.
    # No assessor, outcome, native object, or prior gain is consulted here.
    while len(origins) < FIXED_TIMINGS:
        values = sorted(origins)
        left, right = min(zip(values, values[1:]), key=lambda pair: (-(pair[1] - pair[0]), pair[0]))
        midpoint = left + (right - left) / 2
        if midpoint in origins or not left < midpoint < right:
            raise ValueError("reference:unrefinable_interval")
        origins[midpoint] = [f"longest_interval_midpoint_{len(refinements)}"]
        refinements.append({"left": left, "right": right, "midpoint": midpoint})
    return {"checkpoint_at": study.START, "command_message_delay": COMMAND_DELAY,
        "center_assumptions": "Nominal no-contention public-duration alignment. Source grant and receiving reservation are distinct from physical arrival; native still validates both. Command cannot arrive before checkpoint+0.01.",
        "centers": [{"name": name, "value": value, "formula": formula} for name, value, formula in centers],
        "public_empty_source_and_travel_lead": lead, "public_headway": headway,
        "neighbor_offset_seconds": epsilon, "neighbor_offset_is_protection_tolerance": False,
        "old_windows": old, "seed_windows": seeds, "refinements": refinements,
        "windows": [{"departure": value, "origins": origins[value]} for value in sorted(origins)],
        "covered_interval": [lower, upper], "continuous_optimality": "unknown",
        "outside_interval": "not enumerated; no dominance or feasibility assertion"}


def branch_manifest(plans: dict) -> dict:
    rows = {}
    for gate in study.GATES:
        plan = plans[str(gate)]
        for index, window in enumerate(plan["windows"]):
            rows[f"gate{int(gate)}/fixed_{index:02d}"] = {
                "gate": gate, "initial_next": 1, "departure": window["departure"],
                "status": "unknown_unexecuted", "kind": "fixed_initial_route"}
        rows[f"gate{int(gate)}/challenger"] = {"gate": gate, "initial_next": 2,
            "departure": plan["old_windows"][0], "status": "unknown_unexecuted", "kind": "old_joint_choice"}
    if len(rows) > MAX_BRANCHES:
        raise ValueError("reference:branch_budget_exceeded")
    return rows


def assess_gate(rows: dict, plan: dict, expected_ids: set[str]) -> dict:
    expected_actions = {f"fixed_{i:02d}": (1, w["departure"]) for i, w in enumerate(plan["windows"])}
    expected_actions["challenger"] = (2, plan["old_windows"][0])
    expected_keys = {f"fixed_{i:02d}" for i in range(FIXED_TIMINGS)} | {"challenger"}
    baseline_keys = [k for k, action in expected_actions.items() if action == (1, plan["old_windows"][1])]
    baseline_key = baseline_keys[0] if len(baseline_keys) == 1 else None
    observed_baselines = [k for k, r in rows.items() if (r.get("initial_next"), r.get("departure")) == (1, plan["old_windows"][1])]
    def action_valid(key, row):
        return key in expected_actions and (row.get("initial_next"), row.get("departure")) == expected_actions[key]

    def valid(row):
        s = row.get("summary", {})
        completed = s.get("completion", {})
        return (row.get("status") == "assessed" and s.get("status") == "assessed" and set(completed) == expected_ids
                and all(isinstance(t, (int, float)) and not isinstance(t, bool)
                        and math.isfinite(t) and 0 <= t <= study.HORIZON for t in completed.values())
                and s.get("common_horizon_complete") is True and s.get("business_complete") is True
                and s.get("all_transfers_received") is True and s.get("all_routes_updated") is True
                and s.get("same_L_two_returns_and_two_reloads") is True
                and s.get("chosen_routes_match_executed_edges") is True
                and s.get("audit", {}).get("status") == "passed")

    baseline = rows.get(baseline_key, {})
    baseline_valid = (baseline_key is not None and observed_baselines == [baseline_key]
                      and action_valid(baseline_key, baseline) and valid(baseline))
    evaluated = {}
    for key, row in rows.items():
        comparable = baseline_valid and action_valid(key, row) and valid(row)
        completed = row.get("summary", {}).get("completion", {})
        delta = ({j: completed[j] - baseline["summary"]["completion"][j] for j in expected_ids}
                 if comparable else None)
        evaluated[key] = {"status": "assessed" if comparable else "unknown",
            "departure": row.get("departure"), "completion": completed,
            "completion_sum": sum(completed.values()) if comparable else None,
            "per_job_delta_vs_original_incumbent": delta,
            "all_offered_protected": comparable and all(d <= 0 for d in delta.values())}
    complete = (set(expected_actions) == expected_keys and set(rows) == expected_keys
                and all(v["status"] == "assessed" for v in evaluated.values()))
    eligible = [k for k, r in evaluated.items() if k.startswith("fixed_") and r["all_offered_protected"]]
    observed = min(eligible, key=lambda k: (evaluated[k]["completion_sum"], evaluated[k]["departure"])) if eligible else None
    best = observed if complete else None
    challenger = evaluated.get("challenger", {})
    advantage = (evaluated[best]["completion_sum"] - challenger["completion_sum"]
                 if best and challenger.get("all_offered_protected") else None)
    return {"status": "complete_finite_reference" if complete else "unknown_incomplete_domain",
        "baseline_key": baseline_key, "expected_branch_count": FIXED_TIMINGS + 1,
        "retained_branch_count": len(rows), "cells": evaluated,
        "best_protected_fixed_timing": best, "best_observed_protected_fixed_timing_not_minimum_claim": observed,
        "challenger_advantage_over_finite_fixed_seconds": advantage,
        "old_challenger_strictly_beaten_or_tied": advantage <= 0 if advantage is not None else None,
        "continuous_fixed_timing_optimum": "unknown", "online_solver": False,
        "complete_100ms_requirement_certified": False}


def read_gzip(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def verify_unchanged_continuation(archive: Path) -> dict:
    current = ast.parse(Path(study.__file__).read_text(encoding="utf-8"))
    frozen = ast.parse(archive.read_text(encoding="utf-8"))
    names = ["Transport", "latest_demand", "later_route", "request_route", "continue_branch"]
    def nodes(tree):
        return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if hasattr(n, "name")}
    a, b = nodes(current), nodes(frozen)
    result = {name: a.get(name) == b.get(name) and name in a for name in names}
    if not all(result.values()):
        raise ValueError("reference:old_continuation_changed")
    return result


def worker(args) -> int:
    output, old = args.output, args.original_study
    sources = [Path(__file__), Path(study.__file__), Path(study.__file__).with_name("native_host.py"),
               Path(study.__file__).with_name("original_workload.py"), Path("scripts/eval/run_g4irsf28_service_potential.py")]
    archived = output / "source_archive"
    archived.mkdir()
    for p in sources:
        (archived / p.name).write_bytes(p.read_bytes())
    receipt = {"schema": "g31.lt2.stronger_timing_reference.v1", "status": "preparing", "command": sys.argv,
        "source_before": {str(p): digest(p) for p in sources}, "source_changed": [],
        "binary_sha256": digest(args.binary), "original_study": str(old), "regimes": {}}
    started = time.perf_counter()
    ledger = {}
    try:
        receipt["unchanged_continuation_ast"] = verify_unchanged_continuation(old / "source_archive" / Path(study.__file__).name)
        prepared, plans, evidence_hashes = {}, {}, {}
        for gate in study.GATES:
            folder = old / f"gate{int(gate)}"
            input_path, raw_path = folder / "input.json", folder / "route1_window1.json.gz"
            data = json.loads(input_path.read_text(encoding="utf-8"))
            raw = read_gzip(raw_path)
            if data != json.loads(json.dumps(study.scene(gate))):
                raise ValueError("reference:old_input_mismatch")
            prepared[str(gate)] = {"input": data, "seed_views": raw["seed_views"],
                "checkpoint_identity": raw["checkpoint_identity"], "original_incumbent_completion": raw["summary"]["completion"]}
            plans[str(gate)] = candidate_plan(data, raw["seed_views"])
            evidence_hashes.update({str(p): digest(p) for p in (input_path, raw_path)})
        ledger = branch_manifest(plans)
        protocol = {"schema": "g31.lt2.stronger_timing_protocol.v1", "maximum_native_branches": MAX_BRANCHES,
            "planned_branch_count": len(ledger), "gates": plans, "original_evidence_hashes": evidence_hashes,
            "branch_manifest": ledger, "fixed_initial_next": 1, "joint_challenger_initial_next": 2,
            "candidate_construction_uses_outcomes": False, "policy_uses_offline_fork_labels": False,
            "protection": "Every four offered-job completion <= same-gate original route1/window1. Exact <=0; no tolerance.",
            "common_continuation": "Byte/AST-equivalent imported original continuation, including later adaptive R1, .05s ticks and .5s retries",
            "hypothesis": "The four-window 1.41s comparison may disappear under a stronger timing family; either outcome is retained",
            "limits": "Finite offline reference on [.11,6.11], not continuous optimality, online solver, B2/B3/B4 implementation or 100ms certification"}
        write_json(output / "preregistered_protocol.json", protocol)
        write_json(output / "branch_ledger.json", ledger)
        if receipt["binary_sha256"] != args.expected_binary_sha256:
            raise ValueError("reference:binary_identity_mismatch")
        native = load_native(args.binary)
        for gate in study.GATES:
            key = str(gate)
            destination = output / f"gate{int(gate)}"
            destination.mkdir()
            frozen = prepared[key]
            data = frozen["input"]
            write_json(destination / "input.json", data)
            parent = native.NativeSession(data)
            parent.advance_to(.05)
            seed = study.Transport(parent)
            channels = {owner: seed.submit(owner, "demand", "seed-demand", target_owner=recipient,
                message_delay=.01, publication_delay=.01) for owner, recipient in [("A", "B"), ("B", "A")]}
            parent.advance_to(study.START)
            seed.refresh(retry=False)
            views = {o: parent.observe_protocol(o) for o in ("A", "B")}
            checkpoint = parent.offline_state_sha256()
            if checkpoint != frozen["checkpoint_identity"] or json.loads(json.dumps(views)) != frozen["seed_views"]:
                raise ValueError("reference:checkpoint_or_information_mismatch")
            if candidate_plan(data, views) != plans[key]:
                raise ValueError("reference:plan_drift")
            rows = {}
            for fullkey, specification in ledger.items():
                if specification["gate"] != gate:
                    continue
                label = fullkey.split("/")[1]
                try:
                    specification["status"] = "unknown_in_progress"
                    write_json(output / "branch_ledger.json", ledger)
                    branch = parent.fork()
                    if branch.offline_state_sha256() != checkpoint:
                        raise ValueError("reference:fork_checkpoint_mismatch")
                    client = study.Transport(branch)
                    client.rows, client.calls = copy.deepcopy(seed.rows), copy.deepcopy(seed.calls)
                    if specification["initial_next"] == 2:
                        tray = next(t for t in views["A"]["trays"] if t["tray_id"] == "L")
                        study.request_route(client, "A", tray, 2, "initial-route")
                    client.submit("B", "transfer", "initial-supply", tray_id="E", source=5, destination=1,
                        earliest_departure=specification["departure"], expiry=study.HORIZON - 1., message_delay=COMMAND_DELAY)
                    continuation = study.continue_branch(branch, client, channels)
                    result = branch.result_at(study.HORIZON)
                    summary = study.assess_cell(data, result, client, continuation, specification["initial_next"])
                    raw = {"checkpoint_identity": checkpoint, "seed_views": views, "specification": copy.deepcopy(specification),
                        "calls": client.calls, "outbox": client.rows, "continuation": continuation, "result": result, "summary": summary}
                    with gzip.open(destination / f"{label}.json.gz", "wt", encoding="utf-8") as stream:
                        json.dump(raw, stream, allow_nan=False)
                    specification.update(status=summary["status"], summary=summary)
                except Exception:
                    specification.update(status="unknown_failed", exception=traceback.format_exc())
                    write_json(destination / f"{label}.failed.json", specification)
                rows[label] = specification
                write_json(output / "branch_ledger.json", ledger)
            report = assess_gate(rows, plans[key], {j["business_bag_id"] for j in data["jobs"]})
            report["checkpoint_identity"] = checkpoint
            baseline = report["cells"].get(report["baseline_key"], {})
            report["original_incumbent_replayed_exactly"] = baseline.get("completion") == frozen["original_incumbent_completion"]
            if not report["original_incumbent_replayed_exactly"]:
                raise ValueError("reference:old_incumbent_not_reproduced")
            receipt["regimes"][key] = report
            write_json(output / "receipt.json", receipt)
        receipt["status"] = "executed" if all(r["status"] == "complete_finite_reference" for r in receipt["regimes"].values()) else "completed_with_unknowns"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["source_changed"] = [str(p) for p in sources if digest(p) != receipt["source_before"][str(p)]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["branch_status_counts"] = {status: sum(r["status"] == status for r in ledger.values()) for status in sorted({r["status"] for r in ledger.values()})}
    receipt["wall_seconds"] = time.perf_counter() - started
    receipt["complete_100ms_requirement_certified"] = False
    write_json(output / "receipt.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"regimes", "source_before"}}, indent=2))
    return int(receipt["status"] != "executed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--original-study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=60.)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    started = time.perf_counter()
    with (args.output / "stdout.txt").open("w", encoding="utf-8") as stdout, (args.output / "stderr.txt").open("w", encoding="utf-8") as stderr:
        try:
            run = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout_seconds, check=False)
            status, code = "finished", run.returncode
        except subprocess.TimeoutExpired:
            status, code = "hard_timeout", 124
    write_json(args.output / "process.json", {"status": status, "exit_code": code,
        "timeout_seconds": args.timeout_seconds, "wall_seconds": time.perf_counter() - started,
        "command": command, "maximum_native_workers": 1,
        "unknown_rule": "Unstarted ledger rows remain unknown_unexecuted; interrupted active rows remain unknown_in_progress; no partial .gz certifies completion"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
