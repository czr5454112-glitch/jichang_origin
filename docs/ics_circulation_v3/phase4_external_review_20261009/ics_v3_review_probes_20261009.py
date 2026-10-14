#!/usr/bin/env python3
"""Read-only diagnostic probes for the isolated ICS V3 prototype.

Prepared from source review of commit 030493a399cdcac3fc005fe2f2cd8ec30fc96277.
The authoring environment syntax-checked this file but DID NOT execute it against
that repository. Run it in a disposable copy of the repository; it is not a
substitute for the original tests, an independent simulator, or a field trial.

Findings being exposed are NOT tests that the repaired implementation must keep.
A diagnostic flag becoming false may be the intended consequence of a repair.
No network access, training, historical-result overwrite or repository mutation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sys
import traceback
from typing import Any

FROZEN_COMMIT = "030493a399cdcac3fc005fe2f2cd8ec30fc96277"
PREFIX = "scripts/experiments/ics_circulation_v3/"
EXPECTED_SHA256 = {
    "model.py": "b25c342097c17c714f874c865ffa10094737bcfd52e599598fc49af27b529235",
    "runtime.py": "b737bdd4082992547e28ba82e449e691230d64bbde8977842e59b08d834a8794",
    "routing.py": "17b3842f133ca0c410bd275fe2a96af3f416add929850529d609326d7feb9224",
    "evaluation.py": "9e5defba24c21e8c1dd23f2c044524996a1acf1ebfb0bf356916d2be3216efee",
    "learning.py": "024b79b8df4a01e2104a465aba9d85c2d5779d19164c9134d9e4eefcee01b3b4",
    "prebalance.py": "bfba7869bd18d78fa9bd1e9c694d73b4072ec0b3bccdaa6d0c0a2f9b12e37cda",
    "request_service.py": "f74e81ac19131d199e38de541008c527f189b44594d16cb1346d44c9fa26f0df",
    "phase2_scenarios.py": "2212c0aab5592acd80b7e0b1b64a667a47555459300eadc1974acf697ba9aeef",
}
PKG = "scripts.experiments.ics_circulation_v3"


def load_modules(root: Path) -> dict[str, Any]:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    modules = {name: importlib.import_module(f"{PKG}.{name}")
               for name in ("model", "runtime", "routing", "prebalance",
                            "request_service", "phase2_scenarios")}
    for name, module in modules.items():
        expected = (root / PREFIX / f"{name}.py").resolve()
        if Path(module.__file__).resolve() != expected:
            raise RuntimeError(f"Imported {name} from an unexpected location: {module.__file__}")
    return modules


def route_dict(candidate: Any) -> dict[str, Any]:
    return asdict(candidate)


def internal_bypass_missing(m: dict[str, Any]) -> dict[str, Any]:
    """One region, two paths; booked short path must not erase feasible bypass."""
    d, rt, r = m["model"], m["runtime"], m["routing"]
    nodes = {n: d.Node(n, "z", "one-region", capacity=6 if n in {"S", "G"} else 1)
             for n in ("S", "U", "V", "G")}
    edges = {e.edge_id: e for e in (
        d.Edge("S-U", "S", "U", 1), d.Edge("U-G", "U", "G", 1),
        d.Edge("S-V", "S", "V", 2), d.Edge("V-G", "V", "G", 2),
    )}
    bag = d.Bag("target", "S", "G", 0, 100)
    trays = {"target": d.Tray("target", "S", "loaded", "target")}
    trays.update({f"b{i}": d.Tray(f"b{i}", "S") for i in range(5)})
    state = d.Snapshot(0, d.Network(nodes, edges), trays, {"target": bag})
    validator = rt.ExecutionValidator()
    for i in range(5):
        key = f"blocker:{i}"
        plan = d.RouteCandidate(key, None, f"b{i}",
            (d.Leg("S-U", i, i + 1), d.Leg("U-G", i + 1, i + 2)),
            i + 2, i + 2, state.version, key, True, "G")
        verdict = validator.commit(state, plan)
        if not verdict.accepted:
            raise RuntimeError(f"Counterexample setup rejected: {verdict.reason}")
    rt.assert_invariants(state)
    regional = r.RegionalCandidateGenerator(horizon=4, expansion_limit=100000,
                                           static_path_limit=64, deadline_ms=None)
    flat = rt.CandidateGenerator(horizon=4, expansion_limit=100000)
    a = regional.generate(state.clone(), "target", "target", 3)
    b = flat.generate(state.clone(), "target", "target", 1)
    b_valid = [validator.validate(state, c).accepted for c in b]
    return {
        "kind": "bounded_candidate_coverage_gap_not_a_safety_violation",
        "setup": "S-U-G statically length 2 but S-U booked on [0,5); S-V-G length 4 is free; horizon 4; all nodes in one control region",
        "regional_status": regional.last_search_status,
        "regional_candidates": [route_dict(c) for c in a],
        "flat_status": flat.last_search_status,
        "flat_candidates": [route_dict(c) for c in b],
        "flat_candidates_pass_same_validator": b_valid,
        "diagnostic_exposed": not a and bool(b) and all(b_valid),
        "repair_goal": "Discover an authorized local bypass within the declared budget; do not relabel bounded_no_candidate as physical infeasibility",
    }


def prefix_release_omission(m: dict[str, Any]) -> dict[str, Any]:
    """Conservative firm supply is correct; inspect missing separate forecast."""
    d, rt, p = m["model"], m["runtime"], m["prebalance"]
    nodes = {n: d.Node(n, "z", f"r:{n}") for n in ("S", "M", "G")}
    edges = {e.edge_id: e for e in (d.Edge("S-M", "S", "M", 1), d.Edge("M-G", "M", "G", 1))}
    bag = d.Bag("target", "S", "G", 0, 50)
    initial = d.Snapshot(0, d.Network(nodes, edges),
        {"target": d.Tray("target", "S", "loaded", "target")}, {"target": bag})
    c = d.RouteCandidate("candidate", "target", "target", (d.Leg("S-M", 0, 1), d.Leg("M-G", 1, 2)),
                         3, 3, 0, "candidate", True, "G")
    full, prefix = initial.clone(), initial.clone()
    validator = rt.ExecutionValidator()
    for state, mode in ((full, "whole_route"), (prefix, "next_edge")):
        verdict = validator.commit(state, c, route_mode=mode)
        if not verdict.accepted:
            raise RuntimeError(f"Counterexample setup rejected: {verdict.reason}")
        rt.assert_invariants(state)
    full_supply = [asdict(s) for s in p.known_supply(full)]
    prefix_supply = [asdict(s) for s in p.known_supply(prefix)]
    return {
        "kind": "firm_supply_vs_conditional_prediction_interface_gap",
        "original_full_candidate": route_dict(c),
        "committed_safe_prefix": route_dict(prefix.plans["target"]),
        "whole_route_known_supply": full_supply,
        "next_edge_known_supply": prefix_supply,
        "snapshot_fields": list(prefix.__dataclass_fields__),
        "diagnostic_exposed": bool(full_supply) and not prefix_supply and prefix.plans["target"].prefix_only,
        "interpretation": "Never count a tentative release as firm stock. Add a separately versioned conditional release forecast; a safe stop is not an empty tray release.",
        "repair_goal": "Keep correct firm-supply accounting AND make tentative remaining-route releases available to prediction with explicit dependencies",
    }


def unexecuted_suffix_not_updatable(m: dict[str, Any]) -> dict[str, Any]:
    d, rt, r, q = m["model"], m["runtime"], m["routing"], m["request_service"]
    nodes = {n: d.Node(n, "z", f"r:{n}") for n in ("S", "U", "V", "G")}
    edges = {e.edge_id: e for e in (
        d.Edge("S-U", "S", "U", 1), d.Edge("U-G", "U", "G", 1),
        d.Edge("S-V", "S", "V", 3), d.Edge("V-G", "V", "G", 3),
    )}
    bag = d.Bag("target", "S", "G", 0, 50)
    state = d.Snapshot(0, d.Network(nodes, edges),
        {"target": d.Tray("target", "S", "loaded", "target")}, {"target": bag})
    c = d.RouteCandidate("old", "target", "target", (d.Leg("S-V", 5, 8), d.Leg("V-G", 8, 11)),
                         12, 12, 0, "old", True, "G")
    verdict = rt.ExecutionValidator().commit(state, c, route_mode="whole_route")
    if not verdict.accepted:
        raise RuntimeError(f"Counterexample setup rejected: {verdict.reason}")
    calls = {"generator_factory": 0}
    def factory():
        calls["generator_factory"] += 1
        return r.RegionalCandidateGenerator(horizon=30, deadline_ms=None)
    owner = q.ResourceOwner(state)
    before = owner.snapshot()
    request = q.RouteRequest("new-update-request", "target", "target", route_mode="whole_route")
    result = q.RoutingRequestService(owner, generator_factory=factory).handle(request)
    return {
        "kind": "old_route_fallback_is_not_general_suffix_replanning",
        "all_old_departures_in_future": all(leg.depart > state.now for leg in c.legs),
        "old_route": route_dict(c), "result": asdict(result),
        "generator_factory_calls": calls["generator_factory"],
        "owner_state_unchanged": owner.snapshot() == before,
        "diagnostic_exposed": result.status == "still_valid_old_route" and calls["generator_factory"] == 0,
        "interpretation": "This exposes the current fallback contract, not an idempotency defect. A future explicit update request must distinguish keep-valid from recompute intent and authorized suffix replacement.",
        "repair_goal": "Add request intent and atomic replacement of legally revocable future suffixes; preserve entered segments and service commitments",
    }


def family_constraint_activity(m: dict[str, Any]) -> dict[str, Any]:
    scenes = m["phase2_scenarios"].phase2_scenes()
    rows = []
    for scene in scenes:
        n = len(scene.initial.trays)
        cap = min(node.capacity for node in scene.initial.network.nodes.values())
        bags = list(scene.initial.bags.values()) + list(scene.future(0))
        rows.append({"source_group": scene.source_group, "nodes": len(scene.initial.network.nodes),
                     "trays": n, "min_node_capacity": cap, "bag_count": len(bags),
                     "all_nodes_waitable": all(v.can_wait for v in scene.initial.network.nodes.values()),
                     "protected_bag_count": sum(b.protected for b in bags),
                     "node_capacity_cannot_bind_by_finite_tray_count": n < cap})
    return {
        "kind": "structural_activity_audit_no_new_generalization_evidence",
        "source_count": len(rows),
        "tray_count_range": [min(r["trays"] for r in rows), max(r["trays"] for r in rows)],
        "bag_count_range": [min(r["bag_count"] for r in rows), max(r["bag_count"] for r in rows)],
        "diagnostic_exposed": all(r["node_capacity_cannot_bind_by_finite_tray_count"] for r in rows),
        "all_nodes_waitable": all(r["all_nodes_waitable"] for r in rows),
        "protected_bags_total": sum(r["protected_bag_count"] for r in rows),
        "qualification": "Edge capacity and reception capacity CAN bind; this does not establish absence of all congestion.",
        "rows": rows,
    }


def identical_prefix_distinct_full_candidates(m: dict[str, Any]) -> dict[str, Any]:
    rt, r = m["runtime"], m["routing"]
    scene = m["phase2_scenarios"].make_scene(0, "train")
    state = scene.initial.clone()
    generator = r.RegionalCandidateGenerator(horizon=scene.horizon, deadline_ms=None)
    candidates = generator.generate(state, scene.target_bag, scene.target_tray, 4)
    groups: dict[str, list[str]] = {}
    prefixes = []
    for candidate in candidates:
        copy = state.clone()
        verdict = rt.ExecutionValidator().commit(copy, candidate, route_mode="next_edge")
        if not verdict.accepted:
            raise RuntimeError(f"Counterexample setup rejected: {verdict.reason}")
        prefix = copy.plans[candidate.tray_id]
        # Ignore diagnostic IDs and the baseline flag. Include all physical and
        # obligation fields actually relevant to this prototype's next state.
        key = json.dumps({"legs": [asdict(leg) for leg in prefix.legs],
                          "destination": prefix.destination_node,
                          "continuation_destination": prefix.continuation_destination,
                          "prefix_only": prefix.prefix_only,
                          "unload_complete": prefix.unload_complete,
                          "usable_at": prefix.usable_at}, sort_keys=True)
        groups.setdefault(key, []).append(candidate.candidate_id)
        prefixes.append({"candidate": route_dict(candidate), "committed": route_dict(prefix)})
    return {
        "kind": "candidate_identity_vs_executed_action_identity",
        "source_group": scene.source_group, "decision_node": state.trays[scene.target_tray].node,
        "full_candidate_count": len(candidates), "distinct_physical_prefixes": len(groups),
        "diagnostic_exposed": len(candidates) > len(groups), "candidates_and_prefixes": prefixes,
        "qualification": "Phase-3 labels were collected at S (tick 2), not this A state. This probe concerns deployment action identity and future data collection, not proof that those S labels are duplicates.",
        "repair_goal": "Group actual interventions, including any newly retained tentative-plan state; do not mistake different discarded suffixes for different executed actions",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-modified", action="store_true",
                        help="Allow post-repair source; outputs explicitly cease to be frozen-commit observations")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; use a new file, never overwrite evidence")
    hashes = {}
    for name, expected in EXPECTED_SHA256.items():
        path = root / PREFIX / name
        if not path.is_file():
            parser.error(f"Missing source file: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[name] = {"sha256": actual, "expected_sha256": expected, "matches": actual == expected}
    all_match = all(row["matches"] for row in hashes.values())
    if not all_match and not args.allow_modified:
        names = [name for name, row in hashes.items() if not row["matches"]]
        parser.error(f"Source differs from supplied frozen manifest: {names}; --allow-modified is for explicit repair checks only")
    result: dict[str, Any] = {
        "schema": "ics_v3_source_review_probes_v1", "prepared_for_commit": FROZEN_COMMIT,
        "execution_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "repository_root": str(root), "source_matches_frozen_manifest": all_match,
        "source_hashes": hashes,
        "scope": "Targeted diagnostics using the submitted kernel; not an independent simulator, not field evidence, not a replication of the full original experiment",
        "authoring_status": "Only syntax checked in the report-authoring environment; this invocation supplies actual execution observations",
        "probes": {},
    }
    errors = 0
    try:
        modules = load_modules(root)
    except Exception:
        result["import_error"] = traceback.format_exc()
        errors += 1
    else:
        probes = (internal_bypass_missing, prefix_release_omission,
                  unexecuted_suffix_not_updatable, family_constraint_activity,
                  identical_prefix_distinct_full_candidates)
        for probe in probes:
            try:
                result["probes"][probe.__name__] = {"execution": "completed", **probe(modules)}
            except Exception:
                result["probes"][probe.__name__] = {"execution": "failed", "traceback": traceback.format_exc()}
                errors += 1
    result["execution_error_count"] = errors
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "execution_errors": errors,
                      "note": "diagnostic_exposed=true identifies a review issue; it is NOT a passing quality gate"}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
