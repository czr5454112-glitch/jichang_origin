"""Bounded NEW synthetic overlap domain; conditional pure projection only.

All 96 cells are declared before evaluation. No saved native result or capture
is read. Old model acceptance contracts and native studies remain unchanged.
This is a mechanism diagnostic and baseline comparison, not an online solver.
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
from . import public_reuse_model as engine
from . import research_synthetic_reuse_chain as fixture
from . import native_host, original_workload


VERSION = "conditional_overlap_factorial_v1"
METHODS = ("coordinate_strict", "coordinate_plateau", "resource_pair_repair", "finite_horizon_enumeration")
FIELDS = ("initial_next", "departure", "first_return_delay", "reuse_next")
JOBS = frozenset(("loaded", "receiver", "reuse1", "reuse2"))


def public_domain():
    data = fixture.scene(0.)
    service = {n[0]: n[2] for n in data["node_records"]}
    travel = {(u, v): length / speed for u, v, length, speed in data["edge_records"]}
    first_load_end = next(j["arrival"] + j["load_seconds"] for j in data["jobs"] if j["business_bag_id"] == "loaded")
    paths = ((0, 1, 3, 4), (0, 2, 3, 4))
    arrivals = [first_load_end + sum(service[n] for n in path) + sum(travel[a, b] for a, b in zip(path, path[1:])) for path in paths]
    masking_gate = max(arrivals)
    headway = next(e["entry_headway"] for e in data["edge_contracts"] if (e["from"], e["to"]) == (3, 4))
    late_supply = fixture.START + service[0] + travel[0, 1] + service[1]
    receiver_loads = [fixture.PUBLIC_RECEIVER_LOAD + k * travel[6, 7] for k in range(3)]
    actions = [dict(zip(FIELDS, values)) for values in itertools.product((1, 2), (fixture.START, late_supply), (0., headway), (3, 8))]
    cases = [{"case_id": f"gate{gate_index}_load{load_index}", "storage_gate": gate, "receiver_load": load}
             for gate_index, gate in enumerate((0., masking_gate)) for load_index, load in enumerate(receiver_loads)]
    return {"actions": actions, "cases": cases,
        "incumbent": {"initial_next": 1, "departure": late_supply, "first_return_delay": 0., "reuse_next": 3},
        "derivation": {"initial_storage_path_bounds": arrivals, "masking_gate": masking_gate,
            "receiver_loads": receiver_loads, "receiver_load_formula": "3 + k * public travel(6,7), k=0,1,2",
            "return_wait": headway, "return_wait_formula": "one public edge(3,4) entry headway",
            "late_supply": late_supply, "late_supply_formula": "START + service(0) + travel(0,1) + service(1)",
            "gate0_role": "negative control: route2 extra travel is not masked; keep all strict-protection failures"}}


def protocol():
    domain = public_domain()
    return {"schema": "g31.lt2.new_overlap_domain.v1", "version": VERSION, **domain,
        "maximum_projection_cells": len(domain["cases"]) * len(domain["actions"]), "native_branch_budget": 0,
        "scope": "NEW SYNTHETIC 2-tray/4-job finite projection only; not original-map evidence",
        "invariants": "same graph, FIFO, capacities, edge headways, two physical trays, four full obligations, delays and H40 as declared base fixture",
        "changed_exogenous_contracts": "public receiver load duration and public Storage gate only; equal across all action/method arms within a case",
        "information": "analytically constructed public initial fixture; no authenticated native observations, no future faults, no saved outcomes",
        "model": "existing conditional DiscreteProjection transition engine, fixed four-action continuation subclass; no native validation for these new durations",
        "continuation": "same .05 ticks/.01 wire/.02 ACK/.5 immutable retry and receiving_full recovery in every cell; first return delay selected, second immediate; reuse1 suffix selected, reuse2 suffix3",
        "protection": "all four modeled completion times <= same-case incumbent, exactly zero tolerance; incomplete remains unknown; never a physical certificate",
        "methods": list(METHODS), "evaluation_budget_per_method": 16,
        "ordering": "lexicographic action tuple; score=(sum completion times, action tuple); all methods start from the same incumbent",
        "moves": {"coordinate_strict": "one-coordinate moves, strictly lower objective only",
            "coordinate_plateau": "one-coordinate moves, equal objective allowed, visited-state guard",
            "resource_pair_repair": "up to two coordinates changed per neighborhood, equal objective allowed, visited-state guard; adapted finite destroy/repair baseline",
            "finite_horizon_enumeration": "all16 action tuples, conditional full finite-domain reference, not continuous optimum or online MPC execution"},
        "stop": "declared neighborhood exhausted or16 evaluated candidates; unexecuted cells retained unknown in each strategy trace",
        "causal_contrasts": "full initialR1 x first-return-R2 x laterR1 cube at each fixed supply; per-job/total third differences; strict selected-later versus forced3 ablation",
        "numerics": "strict protection uses no tolerance; a separate1e-9 display threshold only flags interaction distinguishable from floating-point roundoff",
        "limits": ["conditional model, no native permission/ACK/edge execution established", "not actual rolling first-action replanning",
            "not novel optimizer", "not100ms evidence", "a strong baseline tie is a substantive negative result"]}


def make_bundle(case):
    if case not in public_domain()["cases"]: raise ValueError("undeclared_overlap_case")
    data = fixture.scene(0.)
    for job in data["jobs"]:
        if job["business_bag_id"] == "loaded": job["storage_release_at"] = case["storage_gate"]
        if job["business_bag_id"] == "receiver": job["load_seconds"] = case["receiver_load"]
    jobs = {j["business_bag_id"]: {**j, "status": "loaded" if j["business_bag_id"] == "loaded" else "waiting_for_tray",
        "loaded_at": .1 if j["business_bag_id"] == "loaded" else -1.} for j in data["jobs"]}
    return {"contract": data, "jobs": jobs,
        "trays": {"L": {"business_bag_id": "loaded", "node": 0, "mode": "loaded", "edge_from": -1, "edge_to": -1},
            "E": {"business_bag_id": "", "node": 5, "mode": "empty", "edge_from": -1, "edge_to": -1}},
        "now": fixture.START, "online_information_delivered": False,
        "assumptions": ["declared synthetic initial state, not authenticated native capture",
            "existing approximate native-event/FIFO/calendar model; no error bound for new durations"]}


class Projection(engine.DiscreteProjection):
    def __init__(self, bundle, action):
        super().__init__(bundle, {**action, "later_mode": "native_keep"})

    def request(self, key, destination, earliest):
        self.record("MODEL_TRANSFER_INTENT", key, destination=destination, earliest=earliest)
        super().request(key, destination, earliest)

    def tick(self):
        for request in self.requests[:]:
            if not request["terminal"] and self.time >= request["next_retry"]:
                request["next_retry"] = self.time + .5
                self.schedule(self.time + .01, "request_delivery", request)
        e, l = self.trays["E"], self.trays["L"]
        if l["mode"] == "empty" and l["node"] == 6 and self.returns < 2 and not self.return_pending:
            self.returns += 1
            self.request("L", 7, self.time + (self.a["first_return_delay"] if self.returns == 1 else 0.))
        request = self.last_supply
        if request and request["terminal"] and request["ack"] == "rejected" and self.time >= request["ack_at"] + .5 and len([x for x in self.requests if x["tray"] == "E"]) < 16:
            if e["mode"] == "empty" and e["node"] == 5: self.request("E", 1, self.time)
        if l["node"] == 7 and l["mode"] == "loaded" and l["edge_to"] < 0 and l["job"] not in self.choice_jobs:
            self.choice_jobs.add(l["job"])
            chosen = self.a["reuse_next"] if l["job"] == "reuse1" else 3
            self.choices.append({"at": self.time, "job": l["job"], "next": chosen})
            self.schedule(self.time + .01, "route", "L", chosen)


def predict(case, action):
    if action not in public_domain()["actions"]:
        return {"status": "unknown_undeclared_action", "completion": {}}
    return Projection(make_bundle(case), action).run()


def key(action): return tuple(action[f] for f in FIELDS)


def protected(prediction, incumbent):
    if (prediction.get("status") != "conditional_prediction" or incumbent.get("status") != "conditional_prediction"
            or set(prediction.get("completion", {})) != JOBS or set(incumbent.get("completion", {})) != JOBS): return None
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
           for row in (prediction, incumbent) for value in row["completion"].values()): return None
    return all(prediction["completion"][job] <= incumbent["completion"][job] for job in JOBS)


def solve(case, method, *, evaluator=predict, budget=16):
    if method not in METHODS or type(budget) is not int or budget < 1: raise ValueError("invalid_strategy_or_budget")
    domain = {key(action): action for action in public_domain()["actions"]}; base = key(public_domain()["incumbent"])
    cache = {}; hit = False
    def evaluate(candidate):
        nonlocal hit
        if candidate in cache: return cache[candidate]
        if len(cache) >= budget: hit = True; return None
        value = evaluator(case, domain[candidate])
        baseline = cache[base]["prediction"] if base in cache else value
        cache[candidate] = {"action": copy.deepcopy(domain[candidate]), "prediction": value, "model_protected": protected(value, baseline)}
        return cache[candidate]
    evaluate(base)
    score = lambda candidate: (sum(cache[candidate]["prediction"]["completion"].values()), candidate)
    if cache[base]["model_protected"] is True:
        if method == "finite_horizon_enumeration":
            for candidate in sorted(domain):
                if evaluate(candidate) is None: break
        else:
            frontier, expanded = [base], set()
            while frontier and not hit:
                current = min(frontier, key=score); frontier.remove(current)
                if current in expanded: continue
                expanded.add(current); eligible = []
                for candidate in sorted(domain):
                    distance = sum(a != b for a, b in zip(candidate, current))
                    if not (1 <= distance <= (2 if method == "resource_pair_repair" else 1)): continue
                    row = evaluate(candidate)
                    if row is None: break
                    if row["model_protected"] is not True: continue
                    improves = score(candidate)[0] < score(current)[0] if method == "coordinate_strict" else score(candidate)[0] <= score(current)[0]
                    if improves and candidate not in expanded: eligible.append(candidate)
                if method == "coordinate_strict": frontier = [min(eligible, key=score)] if eligible else []
                else: frontier.extend(candidate for candidate in eligible if candidate not in frontier)
    eligible = [candidate for candidate, row in cache.items() if row["model_protected"] is True]
    best = min(eligible, key=score) if eligible else None
    return {"method": method, "status": "conditional_model_selection" if best else "unknown_incumbent_or_no_protected_candidate",
        "selected_action": domain[best] if best else None, "model_gain": score(base)[0] - score(best)[0] if best else None,
        "evaluations": len(cache), "budget": budget, "candidate_denominator": len(domain),
        "stop": "budget_exhausted" if hit else "declared_neighborhood_exhausted",
        "rows": [{**cache[candidate], "evaluation_status": "evaluated"} if candidate in cache else {
            "action": domain[candidate], "evaluation_status": "unknown_unexecuted", "model_protected": None} for candidate in sorted(domain)]}


def assess_case(case, cells):
    domain = public_domain(); lookup = {key(row["action"]): row["prediction"] for row in cells}
    expected = {key(a) for a in domain["actions"]}
    if len(cells) != len(expected) or set(lookup) != expected:
        return {"status": "unknown_incomplete_or_duplicate_factorial", "case": case}
    baseline = lookup[key(domain["incumbent"])]
    coverage = [{"action": row["action"], "status": row["prediction"]["status"], "model_protected": protected(row["prediction"], baseline)} for row in cells]
    cubes = []
    for departure in sorted({a["departure"] for a in domain["actions"]}):
        cube = {key(a): lookup[key(a)] for a in domain["actions"] if a["departure"] == departure}
        known = all(protected(p, p) is True for p in cube.values())
        differences = {job: sum((1 if (int(k[0] == 2) + int(k[2] > 0) + int(k[3] == 8)) % 2 else -1) * p["completion"][job]
                               for k, p in cube.items()) for job in sorted(JOBS)} if known else None
        cubes.append({"departure": departure, "status": "conditional_model_cube" if known else "unknown_incomplete_cube",
            "third_difference_by_job": differences, "third_difference_sum": sum(differences.values()) if differences else None,
            "interaction_above_roundoff_display_threshold": any(abs(x) > 1e-9 for x in differences.values()) if differences else None})
    methods = [solve(case, method, evaluator=lambda c, a: copy.deepcopy(lookup[key(a)])) for method in METHODS]
    ablations = []
    for method in methods:
        action = method["selected_action"]
        if action is None: continue
        no_later = {**action, "reuse_next": 3}
        selected, fixed = lookup[key(action)], lookup[key(no_later)]
        known = protected(selected, selected) is True and protected(fixed, fixed) is True
        ablations.append({"method": method["method"], "selected_action": action, "fixed_later_action": no_later,
            "status": "conditional_paired_model_counterfactual" if known else "unknown_incomplete_counterfactual",
            "completion_fixed3_minus_selected": {job: fixed["completion"][job] - selected["completion"][job] for job in sorted(JOBS)} if known else None,
            "fixed3_model_protected_vs_incumbent": protected(fixed, baseline), "selected_model_protected_vs_incumbent": protected(selected, baseline)})
    return {"status": "complete_conditional_factorial", "case": case, "cell_denominator": len(cells),
        "coverage": coverage, "cubes": cubes, "methods": methods, "later_ablation": ablations,
        "native_feasibility_certified": False, "online_information_delivered": False}


def sources():
    paths = [Path(__file__), Path(engine.__file__), Path(fixture.__file__), Path(native_host.__file__), Path(original_workload.__file__)]
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--execute-pure", action="store_true")
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    plan = protocol(); pins = sources()
    (args.output / "preregistered_protocol.json").write_text(json.dumps({**plan, "source_sha256": pins}, indent=2), encoding="utf-8")
    archive = args.output / "source"; archive.mkdir()
    for name in pins: (archive / Path(name).name).write_bytes(Path(name).read_bytes())
    if not args.execute_pure: return
    started = time.perf_counter(); output = []
    for case in plan["cases"]:
        cells = []
        for action in plan["actions"]:
            try: prediction = predict(case, action)
            except Exception as exc: prediction = {"status": "unknown_projection_exception", "exception": type(exc).__name__ + ":" + str(exc), "completion": {}}
            cells.append({"action": action, "prediction": prediction})
        report = {"case": case, "cells": cells, "assessment": assess_case(case, cells)}
        (args.output / (case["case_id"] + ".json")).write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        output.append({"case": case, "assessment": report["assessment"]})
    receipt = {"schema": "g31.lt2.conditional_overlap_factorial_receipt.v1", "case_count": len(output),
        "cell_count": sum(x["assessment"].get("cell_denominator", 0) for x in output), "native_calls": 0,
        "source_changed": [name for name, digest in pins.items() if sources().get(name) != digest],
        "wall_seconds": time.perf_counter() - started, "results": output,
        "physical_business_protection": "unknown_no_native_execution", "online_rolling_execution": False}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__": main()
