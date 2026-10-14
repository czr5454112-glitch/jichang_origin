"""Independent JSON-only audit; never invokes controllers or simulation."""
from pathlib import Path
from copy import deepcopy
import argparse
import gzip
import hashlib
import json
import random
import time

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
PRIMARY = BASE / "phase4_w3_network_role_labels_parallel_20261009"
NOMINAL = BASE / "phase4_w3_network_nominal_opportunities_repaired_20261010"
OUT = Path(__file__).resolve().parent
INF = 10**30


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Auditor:
    def __init__(self):
        self.checks, self.errors, self.bound = 0, [], {}
        self.guards, self.prefixes, self.slow_calls = 0, 0, 0
        self.distances = {}

    def check(self, okay, label):
        self.checks += 1
        if not okay:
            self.errors.append(label)

    def bind(self, path, expected=None):
        path = Path(path).resolve()
        actual = sha(path)
        self.bound[str(path)] = actual
        if expected is not None:
            self.check(actual == expected, "sha:" + str(path))

    def manifest(self, base, path):
        self.bind(path)
        for name, expected in read(path).items():
            self.bind(Path(base) / name, expected)

    def all_distances(self, network):
        key = digest(network)
        if key not in self.distances:
            # Independent Floyd-Warshall, unlike the implementation's heap search.
            nodes = sorted(network["nodes"])
            index = {node: i for i, node in enumerate(nodes)}
            matrix = [[0 if i == j else INF for j in range(len(nodes))] for i in range(len(nodes))]
            for edge in network["edges"].values():
                if edge["capacity"] > 0:
                    i, j = index[edge["source"]], index[edge["target"]]
                    matrix[i][j] = min(matrix[i][j], edge["travel_time"])
            for k, row in enumerate(matrix):
                for other in matrix:
                    to_k = other[k]
                    if to_k == INF:
                        continue
                    for j, from_k in enumerate(row):
                        other[j] = min(other[j], to_k + from_k)
            self.distances[key] = {n: {m: matrix[i][j] for j, m in enumerate(nodes)} for i, n in enumerate(nodes)}
        return self.distances[key]


def known_supply(state, network):
    result, now = [], state["now"]
    hold = state["module"]["hold_by_node"]
    flights = {f["tray_id"]: f for f in state["old_in_transit"]}
    for tray_id, tray in sorted(state["trays"].items()):
        if tray_id in state["plans"]:
            plan = state["plans"][tray_id]
            if plan["prefix_only"]:
                continue
            destination = state["bags"][plan["bag_id"]]["destination"] if plan["bag_id"] is not None else plan["destination_node"]
            end = network["edges"][plan["legs"][-1]["edge_id"]]["target"] if plan["legs"] else tray["node"]
            if end == destination:
                result.append(dict(tray_id=tray_id, node=destination, at=max(now, plan["usable_at"]), source="committed_release"))
        elif tray_id in flights:
            flight = flights[tray_id]
            node = network["edges"][flight["edge_id"]]["target"]
            ready = flight["arrive"] + hold.get(node, 0)
            if tray["bag_id"] is not None:
                if state["bags"][tray["bag_id"]]["destination"] != node:
                    continue
                ready += state["module"]["unload_ticks"]
            result.append(dict(tray_id=tray_id, node=node, at=max(now, ready), source="old_in_transit_release"))
        elif tray["node"] is not None and tray["mode"] in {"empty", "holding", "unloading"} and tray_id not in state["empty_targets"]:
            result.append(dict(tray_id=tray_id, node=tray["node"], at=max(now, tray["available_at"]), source="stationary_release"))
    return result


def matching(units, supplies, earliest, tick, removed=None, exact=False):
    choices = {u["key"]: [s["tray_id"] for s in supplies if s["tray_id"] != removed and (
        s["node"] == u["node"] and s["at"] <= tick if exact else earliest.get((s["tray_id"], u["node"]), INF) <= tick)] for u in units}
    assigned = {}

    def augment(unit, visited):
        for tray in choices[unit]:
            if tray in visited:
                continue
            visited.add(tray)
            if tray not in assigned or augment(assigned[tray], visited):
                assigned[tray] = unit
                return True
        return False
    return sum(augment(unit["key"], set()) for unit in reversed(units))


def audit_guard(audit, guard, units, state, network, label):
    audit.guards += 1
    donor = guard["tray_id"]
    zone = network["nodes"][state["trays"][donor]["node"]]["logistics_zone"]
    supplies = [s for s in known_supply(state, network) if network["nodes"][s["node"]]["logistics_zone"] == zone]
    audit.check(supplies == guard["supplies"], label + ":supply_from_real_sequential_state")
    regional = [u for u in units if network["nodes"][u["node"]]["logistics_zone"] == zone]
    target = next(u for u in regional if u["key"] == guard["target_key"])
    service = max(target["at"], guard["usable_at"])
    audit.check(service == guard["service_at"], label + ":target_service")
    distances, earliest = audit.all_distances(network), {}
    cutoffs = {state["now"], guard["usable_at"], service, *(u["at"] for u in regional)}
    for supply in supplies:
        for node in {u["node"] for u in regional}:
            distance = distances[supply["node"]][node]
            if distance == INF:
                continue
            ready = supply["at"] if node == supply["node"] else supply["at"] + distance + state["module"]["hold_by_node"].get(node, 0)
            earliest[supply["tray_id"], node] = ready
            cutoffs.add(ready)
    expected_earliest = [dict(tray_id=t, node=n, at=ready) for (t, n), ready in sorted(earliest.items())]
    audit.check(guard.get("earliest_service") == expected_earliest, label + ":shortest_times")
    end = guard["horizon_end"]
    cutoffs = sorted({t for t in cutoffs if state["now"] <= t <= end} | {end})
    rows, reason = [], None
    for tick in cutoffs:
        others = [u for u in regional if u["key"] != target["key"] and u["at"] <= tick]
        credit = int(service <= tick)
        before = matching(others + ([target] if credit else []), supplies, earliest, tick)
        other_before = matching(others, supplies, earliest, tick)
        other_after = matching(others, supplies, earliest, tick, donor)
        firm_before = matching(others, supplies, earliest, tick, exact=True)
        firm_after = matching(others, supplies, earliest, tick, donor, True)
        rows.append(dict(tick=tick, before=before, after=other_after + credit,
            other_before=other_before, other_after=other_after, firm_other_before=firm_before,
            firm_other_after=firm_after, target_credit=credit))
        if other_after < other_before or firm_after < firm_before or other_after + credit < before:
            reason = "same_zone_would_degrade_other_prefix"
            break
    if guard["reason"] == "same_zone_guard_work_budget":
        audit.check(guard["prefixes"] == rows[:len(guard["prefixes"])], label + ":budget_partial_no_approval")
    else:
        audit.check(guard["prefixes"] == rows, label + ":every_event_prefix")
        audit.check(guard["reason"] == reason, label + ":decision")
    audit.prefixes += len(guard["prefixes"])


def physical(value):
    value = deepcopy(value)
    value["policy_stats"] = {k: v for k, v in value.get("policy_stats", {}).items() if not k.endswith("_ms")}
    return value


def expected_demand_units(state, forecasts, horizon):
    """Rebuild business identity demand from original publication data."""
    now, units = state["now"], {}
    carried = {tray["bag_id"] for tray in state["trays"].values() if tray["bag_id"] is not None}
    observed = set(state["bags"]) | set(state["completed"]) | carried
    for bag in state["bags"].values():
        identity = bag["bag_id"]
        if identity not in carried and identity not in state["completed"]:
            key = "identity:" + identity
            units[key] = dict(key=key, node=bag["origin"], at=now,
                source="visible_queue:" + identity, unit_id=identity)
    latest = {}
    for forecast in forecasts:
        if forecast["published_at"] > now:
            continue
        key = forecast["forecast_id"]
        if key not in latest or forecast["published_at"] > latest[key]["published_at"]:
            latest[key] = forecast
    for forecast in latest.values():
        if now - forecast["published_at"] > 60 or (forecast["count"] and forecast["at"] > now + horizon):
            continue
        identities = forecast["unit_ids"] or [forecast["forecast_id"] + ":" + str(i) for i in range(forecast["count"])]
        for identity in identities:
            if identity in observed:
                continue
            key = "identity:" + identity
            units[key] = dict(key=key, node=forecast["node"], at=max(now, forecast["at"]),
                source="overdue_identified_forecast" if forecast["at"] <= now else "published_forecast",
                unit_id=identity)
    return sorted(units.values(), key=lambda u: (u["at"], u["node"], u["source"], u["key"]))


def audit_case(audit, raw, row, original, saved_tape):
    label, network = row["case_id"], original["initial"]["network"]
    audit.check(raw["case"] == {k: row[k] for k in raw["case"]}, label + ":identity")
    audit.check(raw["initial_state"]["module"] == original["initial"]["module"], label + ":unchanged_module")
    contract = deepcopy(raw["active_policy_contract"])
    claimed = contract.pop("active_contract_sha256")
    audit.check(digest(contract) == claimed, label + ":active_policy_contract_hash")
    scalars = contract["effective_controller_scalar_parameters"]
    audit.check(scalars["max_candidates"] == (64 if row["policy"] == "old64" else 32), label + ":declared_cross_budget")
    if row["policy"] == "same_zone32plus32":
        audit.check(scalars["max_same_zone_candidates"] == 32 and scalars["max_guard_work"] == 200000, label + ":declared_extra_budget")
    if row["kind"] == "checkpoint":
        meta = read(NOMINAL / "collections/counterflow/d0040.json")
        audit.check(raw["initial_state"] == meta["state"], label + ":checkpoint_state")
        audit.check(raw["initial_cursor"] == meta["cursor"], label + ":checkpoint_cursor")
        audit.check(raw["forced_intervention"]["next_slow_trigger_at"] == meta["next_slow_trigger_at"], label + ":checkpoint_clock")
        expected = {**meta["state"]["bags"], **{b["bag_id"]: b for b in meta["future_event_engine_only"]}}
    else:
        audit.check(raw["initial_state"] == original["initial"], label + ":initial_state")
        expected = {**original["initial"]["bags"], **{b["bag_id"]: b for b in saved_tape}}
    audit.check(sorted(expected) == raw["expected_task_ids"], label + ":whole_expected_ledger")
    ledger = raw["evaluation_ledger"]
    audit.check([{k: entry[k] for k in expected[entry["bag_id"]]} for entry in ledger] == [expected[k] for k in sorted(expected)], label + ":task_ledger_identity")
    result = raw["result"]
    if result is not None:
        state = result["final_snapshot"]
        for entry in ledger:
            identity = entry["bag_id"]
            audit.check(entry["observed"] == (identity in state["bags"]) and entry["completed_at"] == state["completed"].get(identity) and entry["load_time"] == state["load_times"].get(identity), label + ":ledger_matches_actual_state:" + identity)
        protected = [key for key, bag in expected.items() if bag["protected"]]
        on_time = sum(key in state["completed"] and state["completed"][key] <= expected[key]["deadline"] for key in expected)
        protected_ontime = sum(key in state["completed"] and state["completed"][key] <= expected[key]["deadline"] for key in protected)
        audit.check(raw["metrics"]["on_time"] == on_time and raw["metrics"]["protected_expected"] == len(protected) and raw["metrics"]["protected_on_time"] == protected_ontime, label + ":independent_ontime_metrics")
    if raw["status"] == "controller_quiescent":
        state, now = result["final_snapshot"], raw["stopped_at"]
        audit.check(set(expected) <= state["completed"].keys() and set(expected) <= state["bags"].keys(), label + ":all_tasks_complete")
        audit.check(protected_ontime == len(protected), label + ":all_protected_completed_on_time")
        audit.check(not state["plans"] and not state["empty_targets"], label + ":no_commitments")
        audit.check(all(t["mode"] == "empty" and t["bag_id"] is None and t["available_at"] <= now for t in state["trays"].values()), label + ":all_trays_empty_usable")
        audit.check(set(state["trays"]) == set(original["initial"]["trays"]), label + ":tray_conservation")
        for reservation in state["reservations"]:
            if reservation["end"] <= now:
                continue
            tray = state["trays"][reservation["tray_id"]]
            audit.check(reservation["resource"] == "node:" + tray["node"] and reservation["start"] <= now and reservation["end"] == 10**12, label + ":strict_stationary_occupancy")
        audit.check(now >= raw["forecast_expired_at"] and now >= raw["minimum_observation_at"], label + ":observation_and_ttl")
        milestone = raw["milestones"]["controller_quiescent"]
        audit.check(milestone["time"] - milestone["quiet_since"] >= 2 and milestone["actual_slow_triggers_since"] > 0, label + ":actual_quiet_period")
        components = result["cost_components"]
        wait = sum(state["load_times"][key] - bag["arrival"] for key, bag in expected.items() if key in state["load_times"])
        audit.check(components["tray_wait"] == wait, label + ":actual_queue_wait")
        cargo = {k: t["bag_id"] for k, t in original["initial"]["trays"].items()}
        empty = 0
        for event in result["trace"]:
            if event["event"] == "load":
                cargo[event["tray_id"]] = event["bag_id"]
            elif event["event"] == "unload_complete":
                cargo[event["tray_id"]] = None
            elif event["event"] == "depart" and cargo[event["tray_id"]] is None:
                empty += network["edges"][event["edge_id"]]["travel_time"]
        audit.check(empty == components["empty_distance"], label + ":actual_empty_departures")
        tardy = sum(max(0, state["completed"][key] - bag["deadline"]) for key, bag in expected.items() if not bag["protected"])
        audit.check(tardy == components["nonprotected_tardiness"], label + ":tardiness")
        audit.check(abs(result["total_cost"] - (wait + tardy + .1 * empty)) < 1e-8, label + ":total_cost")
    audit.check(raw["search_calls"] == len(raw["searches"]) and raw["search_work"] == sum(r["work"] for r in raw["searches"]), label + ":all_search_work")
    choices = [o for o in raw["opportunities"] if o["candidate_count"]]
    audit.check(len(choices) == len(raw["selector_history_suffix"]), label + ":all_nonempty_attempts_have_selector")
    for opportunity, selected in zip(choices, raw["selector_history_suffix"]):
        audit.check(all(opportunity[key] == selected[key] for key in ("time", "version", "bag_id", "tray_id", "candidate_count", "candidates")), label + ":actual_opportunity_selector_binding")
        audit.check(selected["chosen"] in opportunity["candidates"], label + ":chosen_belongs_to_actual_pool")
    for opportunity in raw["opportunities"]:
        audit.check(opportunity["candidate_count"] == len(opportunity["candidates"]), label + ":zero_and_nonzero_pool_denominator")
    for number, call in enumerate(raw["slow_calls"]):
        prefix = label + ":slow" + str(number)
        audit.slow_calls += 1
        state, diag = call["snapshot_before"], call["diagnostics"]
        audit.check(call["time"] == state["now"] and call["next_slow_trigger_at_after_clock_advance"] == call["time"] + 2, prefix + ":real_clock")
        audit.check(call["published_forecasts"] == [f for f in original["forecasts"] if f["published_at"] <= call["time"]], prefix + ":publication_only")
        audit.check(known_supply(state, network) == call["known_supply"] == diag["initial_supply"], prefix + ":first_real_release")
        audit.check(diag["committed_count"] == len(call["proposals"]), prefix + ":physical_commit_count")
        if row["policy"] != "same_zone32plus32":
            continue
        audit.check(sum(diag["search_calls_by_domain"].values()) == diag["search_calls"] and max(diag["search_calls_by_domain"].values()) <= 32, prefix + ":separate_candidate_budgets")
        audit.check(diag["guard_work"] <= diag["limits"]["max_guard_work"], prefix + ":guard_work_limit")
        audit.check(diag["guard_work"] == diag["demand_expansion_work"] + sum(g["work"] for g in diag["same_zone_guards"]), prefix + ":all_guard_work_including_rejects")
        units, order = diag["demand_units"], {u["key"]: i for i, u in enumerate(diag["demand_units"])}
        independent_units = expected_demand_units(state, original["forecasts"], diag["horizon_end"] - state["now"])
        audit.check(units == independent_units, prefix + ":complete_independent_identity_demand_ledger")
        for i, guard in enumerate(diag["same_zone_guards"]):
            scratch = deepcopy(state)
            for detail, candidate in zip(diag["proposal_details"], call["proposals"]):
                if order[detail["target_key"]] < order[guard["target_key"]]:
                    scratch["plans"][candidate["tray_id"]] = candidate
            audit_guard(audit, guard, units, scratch, network, prefix + ":guard" + str(i))
    if row["policy"] == "old32":
        if row["kind"] == "checkpoint":
            old = read(NOMINAL / "full" / f"counterflow_d0040_c{row['candidate']}.json.gz")
            audit.check(physical(result) == physical(old["result"]), label + ":old_result")
            audit.check(raw["searches"] == old["searches"], label + ":old_all_queries")
            audit.check(raw["cache_before"] == old["cache_before"], label + ":old_all_cache_fields")
        elif row["tape_id"] == "nominal":
            old = read(PRIMARY / row["scene"] / (row["scene"] + "_collection.json"))
            audit.check(physical(raw["original_endpoint"]["result"]) == physical(old["result"]), label + ":old_original_endpoint")
            audit.check(raw["searches"][:raw["original_endpoint"]["search_calls"]] == old["metadata"]["searches"], label + ":old_endpoint_queries")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment")
    parser.add_argument("stage")
    parser.add_argument("report")
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    audit, experiment = Auditor(), BASE / args.experiment
    audit.bind(Path(__file__))
    protocol, tapes = read(experiment / "protocol.json"), read(experiment / "saved_tapes.json")
    audit.manifest(experiment, experiment / "preparation_manifest.json")
    for name, expected in protocol["source_sha256"].items():
        audit.bind(ROOT / "scripts/experiments/ics_circulation_v3" / name, expected)
    for name, expected in protocol["test_sha256"].items():
        audit.bind(ROOT / "tests" / name, expected)
    audit.bind(ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp",
               "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951")
    for path, expected in protocol["input_sha256"].items():
        audit.bind(path, expected)
    # Reproduce the prespecified environment perturbations from original inputs,
    # independent of the experiment's tape-generation helper.
    tape_rows = []
    for scene, seed in {"cross_cycle": 1307, "counterflow": 1319, "near_full": 1327}.items():
        original = read(PRIMARY / scene / (scene + "_input.json"))
        initial, baseline = original["initial"], original["future_engine_only"]
        generator = random.Random(seed)
        generated = {"nominal": baseline}
        for i in range(8):
            future = []
            for bag in sorted(baseline, key=lambda bag: bag["bag_id"]):
                item = deepcopy(bag)
                if not bag["protected"]:
                    if generator.randrange(8) == 0:
                        continue
                    at = max(initial["now"] + 1, bag["arrival"] + generator.choice((-2, 0, 2)))
                    item["deadline"] += at - bag["arrival"]
                    item["arrival"] = at
                future.append(item)
            generated[f"error{i:02d}"] = sorted(future, key=lambda bag: (bag["arrival"], bag["bag_id"]))
        for tape_id, future in generated.items():
            saved = tapes[scene][tape_id]
            audit.check(future == saved["future_engine_only"], scene + ":" + tape_id + ":independent_fixed_environment_tape")
            audit.check(digest(future) == saved["sha256"], scene + ":" + tape_id + ":tape_sha")
            audit.check(saved["future_task_count"] == len(future) and saved["expected_task_count"] == len(initial["bags"]) + len(future), scene + ":" + tape_id + ":complete_task_count")
            tape_rows.append({"scene": scene, "tape": tape_id, "future_task_count": len(future),
                "protected_future_count": sum(b["protected"] for b in future),
                "protected_initial_count": sum(b["protected"] for b in initial["bags"].values())})
    stage = experiment / args.stage
    audit.manifest(stage, stage / "manifest.json")
    requested, summary = read(stage / "requested_cases.json"), read(stage / "summary.json")
    audit.check(requested == protocol["stage_planned_cases"][args.stage], "predeclared_request_grid")
    audit.check(sorted(r["case_id"] for r in summary["rows"]) == sorted(r["case_id"] for r in requested), "complete_failure_denominator")
    report_rows = []
    for row in summary["rows"]:
        if "file" not in row:
            report_rows.append({"case_id": row["case_id"], "status": row["status"], "not_auditable_physical_raw": True})
            continue
        path = experiment / row["file"]
        audit.bind(path, row["sha256"])
        raw = read(path)
        original = read(PRIMARY / row["scene"] / (row["scene"] + "_input.json"))
        future = () if row["kind"] == "checkpoint" else tapes[row["scene"]][row["tape_id"]]["future_engine_only"]
        audit_case(audit, raw, row, original, future)
        report_rows.append({"case_id": row["case_id"], "recorded_status": row["status"], "physical_status": raw["status"],
            "cost": raw["result"]["total_cost"] if raw["result"] else None,
            "physical_task_count": len(raw["expected_task_ids"]), "actual_loaded_opportunities": len(raw["opportunities"]),
            "zero_candidate_opportunities": sum(not o["candidate_count"] for o in raw["opportunities"]),
            "metrics": raw["metrics"], "old32_comparison_record": raw["old32_replication"]})
    for path, expected in audit.bound.items():
        audit.check(sha(path) == expected, "unchanged_during_audit:" + path)
    result = {"schema": "ics_v3_round6_independent_json_audit_v1", "experiment": args.experiment, "stage": args.stage,
        "checks": audit.checks, "errors": audit.errors, "slow_calls": audit.slow_calls, "guards_recomputed": audit.guards,
        "prefixes_recomputed": audit.prefixes, "bound_file_count": len(audit.bound), "bound_files": audit.bound,
        "rows": report_rows, "cpu_seconds": time.process_time() - cpu, "wall_seconds": time.perf_counter() - started,
        "independent_tape_checks": tape_rows,
        "method": "JSON only; independent Floyd-Warshall and recursive matching, every saved guard and event prefix; no simulation replay"}
    with (OUT / args.report).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"bound_files", "rows"}}))
    return bool(audit.errors)


if __name__ == "__main__":
    raise SystemExit(main())
