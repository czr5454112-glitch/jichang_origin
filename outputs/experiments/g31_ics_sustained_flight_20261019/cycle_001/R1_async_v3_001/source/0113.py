"""New finite three-tray occupancy mechanism; pure conditional projections.

The blocker is a real fifth job on a real third tray, kept in every arm. Its
destination9 avoids silently borrowing a berth from the existing Storage.
No original input, accepted model guard or prior study is modified.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import time
from . import research_rolling_overlap_domain as prior


VERSION = "preexisting_occupancy_3tray_5job_v1"
JOBS = prior.JOBS | {"blocker"}
FIELDS, METHODS = prior.FIELDS, prior.METHODS


def cases():
    return [{"case_id": f"block{bi}_load{li}", "blocker_load": block, "receiver_load": load}
            for bi, block in enumerate((.2, 3.)) for li, load in enumerate((3., 5., 7.))]


def domain(case):
    if case not in cases(): raise ValueError("undeclared_preexisting_occupancy_case")
    base = prior.fixture.scene(0.)
    service = {n[0]: n[2] for n in base["node_records"]}
    travel = {(u, v): length / speed for u, v, length, speed in base["edge_records"]}
    blocked_clear = case["blocker_load"] + service[1]
    loaded_clear = max(.1 + service[0], blocked_clear) + travel[0, 1] + service[1]
    quantum = .001
    times = sorted({prior.fixture.START, prior.public_domain()["incumbent"]["departure"], blocked_clear + quantum, loaded_clear + quantum})
    actions = [dict(zip(FIELDS, row)) for row in itertools.product((1, 2), times, (0., .5), (3, 8))]
    return {"actions": actions, "incumbent": prior.public_domain()["incumbent"],
        "public_derivation": {"blocker_node1_clear_bound": blocked_clear, "loaded_node1_clear_bound_if_E_does_not_preempt": loaded_clear,
            "quantum": quantum, "supply_windows": times,
            "formulas": ["blocker clear = source-known load completion + node1 service",
                "loaded clear = max(original loadend + node0service, blocker clear) + travel0→1 + node1service",
                "extra E windows = each public clear bound + native dispatch quantum .001"],
            "limits": "diagnostic intent timings, not proofs of receiver-lease acquisition or native same-timestamp priority"}}


def protocol():
    return {"schema": "g31.lt2.preexisting_occupancy_domain.v1", "version": VERSION,
        "cases": [{**case, "domain": domain(case), "configuration_sha256": hashlib.sha256(json.dumps(make_bundle(case)["contract"],
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()} for case in cases()], "maximum_projection_cells": 192,
        "native_branch_budget": 0, "methods": list(METHODS), "evaluation_budget_per_method": 32,
        "scope": "NEW SYNTHETIC 3-tray/5-job domain, conditional model only",
        "changes_from_prior_fixture": ["add trayP loading blocker job at1, destination9 via new edge1→9",
            "add node9 capacity1, service.1, no export, one positive-capacity edge1→9 travel1/headway.5",
            "Storage gate0 in all cases; blocker public load.2 or3, receiver public load3/5/7"],
        "invariants_within_comparison": "same full5jobs and3trays, graph, existing capacities/FIFO/headways, Storage, arrival/deadline/load/unload/hold and wire protocol across every arm in a case",
        "initial_knowledge": "all five jobs released by.11; public synthetic own load bounds. Offline assembled fixture is not native-authenticated delivery",
        "purpose": "pre-existing local node1 occupancy can make initial route2 shorten loaded release without an equalizing gate; actual shared emptyL return can change later overlap at3",
        "edge_authority": "1→9 is an ordinary positive-capacity edge in every arm, node1/node9 ownerA; it is the only simple path to blocker destination9, not a private P-only grant. Other tray goals cannot use dead-end9 as a suffix.",
        "fixed_initial_reference": "all16 route1 actions in the same32-action domain, including blocker and loaded clearance windows; finite reference not continuous optimum",
        "strict_protection": "all five modeled completion times <= same-case predeclared incumbent, zero tolerance; partial/nonfinite prediction unknown",
        "methods_contract": "same modeled facts/actions/budget32; strict one-coordinate, plateau one-coordinate, plateau up-to-two-coordinate repair, complete32 enumeration; deterministic tuple ties",
        "continuation": "same.05 activation grid/.01 wire/.02ACK/.5retry/rejection recovery; firstLreturn wait0/.5; firstreuse3/8; secondreturn0/secondreuse3",
        "claims_not_allowed": ["physical/native benefit or protection", "native permission/ACK correctness", "online rolling execution", "solver novelty", "100ms"],
        "failure_retention": "all192 conditional projection rows retained; every unexecuted strategy candidate remains unknown",
        "falsifiable_criteria": ["initial-release mechanism fails if route2 cannot improve loaded completion versus any protected fixed-route1 tuple",
            "later-R1 gain fails if the same selected initial/return actions with fixed3 have identical completion vector",
            "protected combined gain fails if any of5jobs regresses versus predeclared incumbent or compared finite fixed-route reference",
            "joint-method superiority fails when ordinary plateau coordinate matches pair repair and finite enumeration",
            "interaction claim remains unknown for any missing/censored/nonfinite cube row; never infer zero from absent completion"],
        "after_results": "do not add outcome-selected load durations or windows to this study"}


def make_bundle(case):
    domain(case)
    old = next(c for c in prior.public_domain()["cases"] if c["storage_gate"] == 0. and c["receiver_load"] == case["receiver_load"])
    bundle = prior.make_bundle(old); contract = bundle["contract"]
    contract["node_records"] = [list(row) for row in contract["node_records"]]
    contract["node_records"][1][5] = list(contract["node_records"][1][5]) + [9]
    contract["node_records"].append([9, 1, .1, 9, 0, []])
    contract["edge_records"].append([1, 9, 1., 1.])
    contract["node_contracts"].append({"node": 9, "zone": "A", "resource_owner": "A", "control_partition": "partition_A",
        "capacity": 1, "allow_export": False, "allow_receive": True, "export_min_stock": 0})
    contract["edge_contracts"].append({"from": 1, "to": 9, "capacity": 1, "entry_headway": .5})
    contract["trays"].append({"tray_id": "P", "node": 1})
    job = {"business_bag_id": "blocker", "origin": 1, "destination": 9, "arrival": 0., "deadline": 40.,
        "storage_node": -1, "storage_release_at": 0., "storage_min_dwell": 0., "load_seconds": case["blocker_load"],
        "unload_seconds": .1, "hold_seconds": .1, "allow_suffix_reroute": True}
    contract["jobs"].append(copy.deepcopy(job))
    bundle["jobs"]["blocker"] = {**job, "status": "loading", "loaded_at": -1.}
    bundle["trays"]["P"] = {"business_bag_id": "blocker", "node": 1, "mode": "loading", "edge_from": -1,
        "edge_to": -1, "load_end": case["blocker_load"]}
    bundle["assumptions"].append("third source-local loading tray P follows only1→9; no hidden stock or omitted blocker obligation")
    return bundle


class Projection(prior.Projection):
    def choose_next(self, key):
        if key == "P" and self.trays[key]["node"] == 1: return 9
        return super().choose_next(key)

    def run(self):
        self.schedule(self.trays["P"]["load_end"], "load_end", "P")
        return super().run()


def predict(case, action):
    if action not in domain(case)["actions"]: return {"status": "unknown_undeclared_action", "completion": {}}
    return Projection(make_bundle(case), action).run()


def protected(value, baseline):
    for row in (value, baseline):
        if row.get("status") != "conditional_prediction" or set(row.get("completion", {})) != JOBS: return None
        if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in row["completion"].values()): return None
    return all(value["completion"][job] <= baseline["completion"][job] for job in JOBS)


def solve(case, method, lookup, budget=32):
    if method not in METHODS or type(budget) is not int or budget < 1: raise ValueError("invalid_method_or_budget")
    actions = {prior.key(a): a for a in domain(case)["actions"]}; base = prior.key(domain(case)["incumbent"])
    cache = {}; hit = False
    def evaluate(candidate):
        nonlocal hit
        if candidate in cache: return cache[candidate]
        if len(cache) >= budget: hit = True; return None
        value = copy.deepcopy(lookup[candidate]); baseline = cache[base]["prediction"] if base in cache else value
        cache[candidate] = {"action": actions[candidate], "prediction": value, "model_protected": protected(value, baseline)}
        return cache[candidate]
    evaluate(base)
    score = lambda candidate: (sum(cache[candidate]["prediction"]["completion"].values()), candidate)
    if cache[base]["model_protected"] is True:
        if method == "finite_horizon_enumeration":
            for candidate in sorted(actions):
                if evaluate(candidate) is None: break
        else:
            frontier, expanded = [base], set()
            while frontier and not hit:
                current = min(frontier, key=score); frontier.remove(current)
                if current in expanded: continue
                expanded.add(current); eligible = []
                for candidate in sorted(actions):
                    distance = sum(a != b for a, b in zip(candidate, current))
                    if not 1 <= distance <= (2 if method == "resource_pair_repair" else 1): continue
                    row = evaluate(candidate)
                    if row is None: break
                    if row["model_protected"] is not True: continue
                    improvement = score(candidate)[0] < score(current)[0] if method == "coordinate_strict" else score(candidate)[0] <= score(current)[0]
                    if improvement and candidate not in expanded: eligible.append(candidate)
                if method == "coordinate_strict": frontier = [min(eligible, key=score)] if eligible else []
                else: frontier.extend(candidate for candidate in eligible if candidate not in frontier)
    eligible = [candidate for candidate, row in cache.items() if row["model_protected"] is True]
    best = min(eligible, key=score) if eligible else None
    return {"method": method, "status": "conditional_model_selection" if best else "unknown_incumbent_or_protection",
        "selected_action": actions[best] if best else None, "model_gain": score(base)[0] - score(best)[0] if best else None,
        "evaluations": len(cache), "budget": budget, "candidate_denominator": len(actions),
        "stop": "budget_exhausted" if hit else "declared_neighborhood_exhausted",
        "rows": [{**cache[c], "evaluation_status": "evaluated"} if c in cache else {
            "action": actions[c], "evaluation_status": "unknown_unexecuted", "model_protected": None} for c in sorted(actions)]}


def assess(case, cells):
    d = domain(case); expected = {prior.key(a) for a in d["actions"]}; lookup = {prior.key(row["action"]): row["prediction"] for row in cells}
    if len(cells) != len(expected) or set(lookup) != expected: return {"status": "unknown_incomplete_or_duplicate_factorial"}
    baseline = lookup[prior.key(d["incumbent"])]; methods = [solve(case, method, lookup) for method in METHODS]
    eligible_fixed = [(k, p) for k, p in lookup.items() if k[0] == 1 and protected(p, baseline) is True]
    best_fixed = min(eligible_fixed, key=lambda pair: (sum(pair[1]["completion"].values()), pair[0]), default=None)
    selected_ablation = []
    for method in methods:
        action = method["selected_action"]
        if action is None: continue
        p, q = lookup[prior.key(action)], lookup[prior.key({**action, "reuse_next": 3})]
        known = protected(p, p) is True and protected(q, q) is True
        selected_ablation.append({"method": method["method"], "action": action,
            "fixed3_minus_selected_by_job": {job: q["completion"][job] - p["completion"][job] for job in sorted(JOBS)} if known else None,
            "selected_protected_vs_best_finite_fixed_initial": protected(p, best_fixed[1]) if best_fixed else None,
            "fixed3_protected_vs_best_finite_fixed_initial": protected(q, best_fixed[1]) if best_fixed else None})
    cubes = []
    for departure in sorted({a["departure"] for a in d["actions"]}):
        cube = {k: p for k, p in lookup.items() if k[1] == departure}; known = all(protected(p, p) is True for p in cube.values())
        differences = {job: sum((1 if (int(k[0] == 2) + int(k[2] > 0) + int(k[3] == 8)) % 2 else -1) * p["completion"][job]
            for k, p in cube.items()) for job in sorted(JOBS)} if known else None
        cubes.append({"departure": departure, "status": "conditional_model_cube" if known else "unknown_incomplete_cube",
            "third_difference_by_job": differences, "display_nonzero_above_roundoff": any(abs(x) > 1e-9 for x in differences.values()) if differences else None})
    return {"status": "complete_conditional_factorial", "cell_count": len(cells), "methods": methods, "cubes": cubes,
        "coverage": [{"action": row["action"], "prediction_status": row["prediction"]["status"], "model_protected": protected(row["prediction"], baseline)} for row in cells],
        "best_finite_fixed_initial": {"action": dict(zip(FIELDS, best_fixed[0])), "prediction": best_fixed[1]} if best_fixed else None,
        "selected_later_ablation": selected_ablation, "native_protection_certified": False, "online_information_delivered": False}


def sources():
    return {**prior.sources(), str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--execute-pure", action="store_true")
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.mkdir(parents=True); pins = sources(); plan = protocol()
    (args.output / "preregistered_protocol.json").write_text(json.dumps({**plan, "source_sha256": pins}, indent=2), encoding="utf-8")
    archive = args.output / "source"; archive.mkdir()
    for name in pins: (archive / Path(name).name).write_bytes(Path(name).read_bytes())
    inputs = args.output / "inputs"; inputs.mkdir()
    for case in cases(): (inputs / (case["case_id"] + ".json")).write_text(json.dumps(make_bundle(case)["contract"], indent=2, allow_nan=False), encoding="utf-8")
    if not args.execute_pure: return
    started = time.perf_counter(); summaries = []
    for case in cases():
        cells = []
        for action in domain(case)["actions"]:
            try: value = predict(case, action)
            except Exception as exc: value = {"status": "unknown_projection_exception", "exception": type(exc).__name__ + ":" + str(exc), "completion": {}}
            cells.append({"action": action, "prediction": value})
        report = {"case": case, "cells": cells, "assessment": assess(case, cells)}
        (args.output / (case["case_id"] + ".json")).write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        summaries.append({"case": case, "assessment": report["assessment"]})
    receipt = {"schema": "g31.lt2.preexisting_occupancy_receipt.v1", "case_count": len(summaries),
        "cell_count": sum(row["assessment"].get("cell_count", 0) for row in summaries), "native_calls": 0,
        "wall_seconds": time.perf_counter() - started, "source_changed": [name for name, digest in pins.items() if sources().get(name) != digest],
        "results": summaries, "native_business_protection": "unknown_no_native_execution", "online_rolling_execution": False}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__": main()
