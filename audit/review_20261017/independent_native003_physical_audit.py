from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import traceback


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
CURRENT = BASE / "compatible_initial_native_20261017_003/mechanism"
METHODS = ("incumbent", "coordinate_strict", "finite_MPC")
REMAINING_METHODS = ("fixed_initial_MPC", "later_default_MPC", "coordinate_plateau", "pair_repair")
PHYSICAL_EVENTS = frozenset((
    "BAG_ARRIVAL", "LOAD_START", "LOAD_COMPLETE", "EDGE_ENTER", "EDGE_EXIT",
    "STORAGE_ENTER", "STORAGE_RELEASE", "UNLOAD_START", "UNLOAD_COMPLETE",
    "HOLD_START", "HOLD_COMPLETE", "EMPTY_RECEIVED",
))
PHYSICAL_FIELDS = ("time", "event", "business_bag_id", "tray_id", "traversal_id", "node", "from", "to")


def read(path):
    payload = path.read_bytes()
    return json.loads(gzip.decompress(payload) if path.suffix == ".gz" else payload)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, explanation):
    if not condition:
        raise AssertionError(explanation)


def receipt_audit(raw):
    data, result = raw["input"], raw["result"]
    jobs = {row["business_bag_id"]: row for row in data["jobs"]}
    result_jobs = {row["business_bag_id"]: row for row in result["jobs"]}
    require(len(jobs) == len(data["jobs"]) == len(result_jobs), "duplicate or missing business population")
    positions = {row["tray_id"]: row["node"] for row in data["trays"]}
    require(len(positions) == len(data["trays"]), "duplicate tray identity")
    capacities = {row["node"]: row["capacity"] for row in data["node_contracts"]}
    edge_contracts = {(row["from"], row["to"]): row for row in data["edge_contracts"]}
    edge_times = {(row[0], row[1]): max(.001, row[2] / row[3]) for row in data["edge_records"]}
    carried = {identity: None for identity in positions}
    in_flight, last_entry, storage_entries = {}, {}, {}
    stage_times, completion, job_trays = {}, {}, {}
    load_order = defaultdict(list)
    maxima = Counter()
    last_time = float("-inf")
    entered_count = exited_count = 0
    for receipt in result["receipts"]:
        event, at = receipt["event"], receipt["time"]
        require(at >= last_time, "receipt time is not ordered")
        last_time = at
        identity, business = receipt["tray_id"], receipt["business_bag_id"]
        if identity:
            require(identity in positions, "receipt creates an unknown tray")
        if event == "LOAD_START":
            require(business in jobs and identity not in in_flight, "load without parked tray or known business")
            require(carried[identity] is None, "tray reused before previous hold completion")
            require(positions[identity] == jobs[business]["origin"], "load at wrong source")
            require(at >= jobs[business]["arrival"], "load before arrival")
            require(business not in job_trays, "business loaded twice")
            carried[identity] = business
            job_trays[business] = identity
            load_order[jobs[business]["origin"]].append(business)
            stage_times[(business, event)] = at
        elif event in {"LOAD_COMPLETE", "STORAGE_ENTER", "STORAGE_RELEASE", "UNLOAD_START", "UNLOAD_COMPLETE", "HOLD_START", "HOLD_COMPLETE"}:
            require(carried[identity] == business, "business/tray binding changed during loaded lifecycle")
            require(identity not in in_flight, "lifecycle transition while still on edge")
            if event == "LOAD_COMPLETE":
                require(at + 1e-9 >= stage_times[(business, "LOAD_START")] + jobs[business]["load_seconds"], "short loading service")
            elif event == "STORAGE_ENTER":
                require(positions[identity] == jobs[business]["storage_node"], "storage entered at wrong node")
                storage_entries[business] = at
            elif event == "STORAGE_RELEASE":
                require(business in storage_entries, "release without actual storage arrival")
                ready = max(storage_entries[business], jobs[business]["storage_release_at"], storage_entries[business] + jobs[business]["storage_min_dwell"])
                require(at + 1e-9 >= ready, "premature storage release")
            elif event == "UNLOAD_START":
                require(positions[identity] == jobs[business]["destination"], "unload at wrong destination")
                if jobs[business]["storage_node"] >= 0:
                    require((business, "STORAGE_RELEASE") in stage_times, "mandatory storage skipped")
            elif event == "UNLOAD_COMPLETE":
                require(business not in completion, "duplicate unload completion")
                require(at + 1e-9 >= stage_times[(business, "UNLOAD_START")] + jobs[business]["unload_seconds"], "short unloading service")
                completion[business] = at
            elif event == "HOLD_COMPLETE":
                require(at + 1e-9 >= completion[business] + jobs[business]["hold_seconds"], "premature empty availability")
                carried[identity] = None
            stage_times[(business, event)] = at
        elif event == "EDGE_ENTER":
            pair = (receipt["from"], receipt["to"])
            require(identity not in in_flight and positions[identity] == pair[0], "edge entry without physical source")
            require((business or None) == carried[identity], "edge entry has wrong load identity")
            require(pair in edge_times and pair in edge_contracts, "edge not in original graph")
            contract = edge_contracts[pair]
            require(contract["capacity"] > 0, "closed edge entered")
            require(at + 1e-9 >= last_entry.get(pair, float("-inf")) + contract["entry_headway"], "entry headway violation")
            in_flight[identity] = (pair, at, receipt["traversal_id"])
            last_entry[pair] = at
            entered_count += 1
            require(sum(value[0] == pair for value in in_flight.values()) <= contract["capacity"], "edge simultaneous capacity exceeded")
        elif event == "EDGE_EXIT":
            require(identity in in_flight, "exit without entry")
            pair, entered_at, traversal_id = in_flight.pop(identity)
            require(pair == (receipt["from"], receipt["to"]) and traversal_id == receipt["traversal_id"], "traversal identity changed")
            require(at + 1e-9 >= entered_at + edge_times[pair], "travel faster than original edge")
            positions[identity] = pair[1]
            exited_count += 1
        elif event == "EMPTY_RECEIVED":
            require(carried[identity] is None and identity not in in_flight, "received empty is still loaded or in flight")
            require(positions[identity] == receipt["node"], "empty received before physical arrival")
        occupancy = Counter(positions[tray] for tray in positions if tray not in in_flight)
        occupancy.update(value[0][1] for value in in_flight.values())
        for node, count in occupancy.items():
            require(count <= capacities[node], "parked plus incoming node capacity exceeded")
            maxima[node] = max(maxima[node], count)
    require(not in_flight and entered_count == exited_count, "unclosed physical traversal")
    require(set(completion) == set(jobs), "not all offered jobs unloaded")
    for business, job in result_jobs.items():
        require(job["status"] == "completed" and job["completed_at"] == completion[business], "terminal result differs from physical unload")
        require(job["deadline_met"] and completion[business] <= jobs[business]["deadline"], "deadline violation")
        require(data["trays"][job["tray"]]["tray_id"] == job_trays[business], "terminal job tray differs from lifecycle")
    for origin, observed in load_order.items():
        expected = [row["business_bag_id"] for row in sorted(data["jobs"], key=lambda row: row["arrival"]) if row["origin"] == origin]
        require(observed == expected, "source load order violates FIFO")
    require({row["tray_id"] for row in result["trays"]} == set(positions), "terminal tray population changed")
    for tray in result["trays"]:
        require(tray["mode"] == "empty" and tray["job"] == -1 and carried[tray["tray_id"]] is None, "terminal tray is not empty")
        require(tray["node"] == positions[tray["tray_id"]] and tray["edge_to"] == -1, "terminal physical position mismatch")
    loaded_next = next(row["to"] for row in result["receipts"] if row["event"] == "EDGE_ENTER" and row["business_bag_id"] == "loaded")
    reuse_next = {business: next(row["to"] for row in result["receipts"] if row["event"] == "EDGE_ENTER" and row["business_bag_id"] == business) for business in ("reuse1", "reuse2")}
    empty_departure = next(row["time"] for row in result["receipts"] if row["event"] == "EDGE_ENTER" and row["tray_id"] == "E")
    returns = [row["time"] for row in result["receipts"] if row["event"] == "EMPTY_RECEIVED" and row["tray_id"] == "L"]
    require(job_trays["loaded"] == job_trays["reuse1"] == job_trays["reuse2"] == "L" and len(returns) == 2, "same L two-return lifecycle missing")
    for index, business in enumerate(("reuse1", "reuse2")):
        require(stage_times[(business, "LOAD_START")] >= returns[index], "reload before actual same-tray return")
    return {"status": "passed_scoped_independent_receipt_replay", "completion": completion,
            "source_fifo_load_order": dict(load_order), "same_L_two_returns_received_at": returns,
            "job_tray_bindings": job_trays, "tray_count": len(positions), "edge_entries": entered_count,
            "edge_exits": exited_count, "maximum_parked_plus_incoming_by_node": dict(maxima),
            "loaded_actual_next": loaded_next, "reuse_actual_next": reuse_next,
            "E_first_actual_edge_enter": empty_departure,
            "scope_limit": "Checks receipt identities, lifecycle, source FIFO, unload endpoints, edge travel/headway/capacity and parked+incoming node capacity. Does not reconstruct pending reception reservations, planner queues, message authority, hidden state, or future safety."}


def inspect_cell(directory, method):
    path = directory / (method + ".raw.json.gz")
    raw, cell = read(path), read(directory / (method + ".cell.json"))
    require(cell["status"] == "assessed", "cell is not closed and assessed")
    require(digest(path) == cell["raw_artifact"]["sha256"], "raw hash differs from cell")
    physical = receipt_audit(raw)
    require(physical["completion"] == cell["summary"]["completion"] == raw["summary"]["completion"], "summary endpoint mismatch")
    owners = {}
    for owner, initial in raw["initial_owners"].items():
        selection, compatibility = initial["selection"], initial["compatibility"]
        binding = selection["provider_evidence"]["source_binding"]
        proof = binding["before_close"]["proof_binding"]
        require(binding["status"] == "closed_complete65" and binding["close_completed"], "request source binding not closed")
        require(proof["proof_uses"] == proof["maximum_proof_uses"] == 65, "source binding use population mismatch")
        selected_index = compatibility["selected_index"]
        require(selected_index in compatibility["eligible_queried_indices"], "selected component lacks eligible queried witness")
        require(selected_index in selection["accounting"]["query_indices"], "selected component was not actually queried")
        selected_row = next(row for row in selection["candidate_rows"] if row["candidate_index"] == selected_index)
        require(selected_row["action"] == initial["selected_action"] and selected_row["estimated_not_worse"], "selected component differs from protected queried row")
        owners[owner] = {"original_selected_index": selection["selected_index"],
                         "compatible_selected_index": compatibility["selected_index"],
                         "original_proposal_rejected": compatibility["original_proposal_rejected"],
                         "selected_action": initial["selected_action"],
                         "proof_uses": proof["proof_uses"], "source_binding_status": binding["status"],
                         "model_counts": selection["accounting"]["provider_counts"],
                         "queried_indices": selection["accounting"]["queried_indices"]}
    require(owners["A"]["compatible_selected_index"] == 4, "A changed its incumbent component")
    require(all(owners["A"]["selected_action"][key] == owners["B"]["selected_action"][key] for key in ("initial_action", "return_delay")), "B conditional plan differs on A-controlled components")
    if method == "incumbent":
        require(owners["B"]["compatible_selected_index"] == 4, "incumbent B changed its component")
    if method in ("coordinate_strict", "finite_MPC") and directory.name == "mechanism":
        require(owners["B"]["compatible_selected_index"] == 12, "mechanism B does not use vector12")
        require(all(row["original_selected_index"] == 25 and row["original_proposal_rejected"] for row in owners.values()), "original 25 rejection missing")
    issued = next(call["request"] for call in raw["calls"] if call["kind"] == "transfer" and not call["retry"] and call["request"]["request_id"] == raw["initial_owners"]["B"]["native_request_id"])
    require(issued["earliest_departure"] == owners["B"]["selected_action"]["empty_departure"], "actual initial supply request differs from selected component")
    effective = {**owners["A"]["selected_action"], **{key: owners["B"]["selected_action"][key] for key in ("empty_departure", "later_action")}}
    require(effective == raw["summary"]["retrospective_effective_vector"], "retrospective vector differs from actual owner selections")
    require(physical["loaded_actual_next"] == 1 and set(physical["reuse_actual_next"].values()) == {3}, "executed route differs from default components")
    acceptance = read(directory / (method + ".acceptance.json"))
    require(acceptance["status"] == "closed_run_acceptance_passed" and not acceptance["active"] and not acceptance["invalid"], "run source acceptance not closed")
    reference = acceptance["run_reference"]
    require(digest(Path(reference["path"])) == reference["sha256"], "saved acceptance does not reference unchanged run registration")
    return raw, {"raw_path": str(path), "raw_sha256": digest(path), "physical": physical, "owners": owners,
                 "effective_policy_parameter_vector": raw["summary"]["retrospective_effective_vector"],
                 "vector_time_warning": "empty_departure is the proposal parameter, not E's actual edge-enter time; the independent physical replay reports that separately",
                 "reported_assessment": cell["status"], "run_acceptance": acceptance["status"],
                 "saved_run_reference": reference,
                 "strict_protected": raw["summary"]["strict_protected"],
                 "native_model_protection_certified": raw["summary"]["native_model_protection_certified"],
                 "complete_request_100ms_certified": raw["summary"]["complete_request_100ms_certified"]}


def parity(new):
    path = BASE / "live_obligation_unloading_native_prepare_001/mechanism/vector_04.json.gz"
    old = read(path)
    expected = read(ROOT / "audit/review_20261017/20261016_review_regressions.json")["evidence_hashes"]["mechanism/vector_04"]["raw_sha256"]
    require(digest(path) == expected, "old vector04 hash differs from saved regression")
    selected = [[row for row in raw["result"]["receipts"] if row["event"] in PHYSICAL_EVENTS] for raw in (old, new)]
    projected = [[{key: row[key] for key in PHYSICAL_FIELDS} for row in rows] for rows in selected]
    require(len(selected[0]) == len(selected[1]) == 78 and selected[0] == selected[1], "predeclared physical receipt scope differs")
    left, right = old["result"]["receipts"], new["result"]["receipts"]
    differences = [{"index": index, "old": before, "new": after} for index, (before, after) in enumerate(zip(left, right)) if before != after]
    require(len(left) == len(right) == 153 and differences, "expected protocol scope difference absent")
    return {"old_raw_path": str(path), "old_raw_sha256": digest(path), "predeclared_events": sorted(PHYSICAL_EVENTS),
            "predeclared_fields": PHYSICAL_FIELDS, "selected_rows": 78,
            "eight_field_projection_exact": projected[0] == projected[1], "selected_all_ten_fields_exact": selected[0] == selected[1],
            "sorting_rounding_id_renaming_or_other_normalization": False,
            "projection_sha256": hashlib.sha256(json.dumps(projected[0], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
            "input_exact": old["input"] == new["input"], "terminal_jobs_exact": old["result"]["jobs"] == new["result"]["jobs"],
            "terminal_trays_exact": old["result"]["trays"] == new["result"]["trays"], "all_receipt_count": 153,
            "all_receipts_exact": False, "different_receipt_count": len(differences), "first_protocol_difference": differences[0],
            "scope_limit": "Only the predeclared 78 physical receipts have exact parity. The full protocol stream and top-level schemas do not."}


def historical_source_archive(directory):
    path = directory / "preregistered_protocol.json"
    manifest = read(path)
    entries = []
    for live_path, relative in manifest["source_archive"].items():
        archive = directory / relative
        expected = manifest["source_sha256"][live_path]
        actual = digest(archive)
        require(actual == expected, "historical archive differs from registered generation: " + relative)
        entries.append({"archived_path": str(archive), "sha256": actual})
    return {"registration_path": str(path), "registration_sha256": digest(path),
            "archived_sources_checked": len(entries), "all_archived_sources_match": True,
            "archive_entries": entries, "live_sources_checked": 0,
            "scope": "Historical archived source generation and saved closed acceptance only. No claim that current live production sources still match."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--campaign", choices=("003", "004", "004+006"), default="003")
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to overwrite existing evidence")
    report = {"schema": "g31.independent_native_raw_physical_audit.v2", "script_sha256": digest(Path(__file__)),
              "campaign": args.campaign,
              "native_calls": 0, "model_calls": 0, "imports_production_auditor": False, "production_edits": [],
              "scope": "Independent reads and arithmetic over saved raw receipts only; not a simulation or universal safety proof."}
    try:
        scenario_names = ("mechanism",) if args.campaign == "003" else ("mechanism", "no_overlap", "insufficient_advance")
        primary_campaign = "004" if args.campaign == "004+006" else args.campaign
        methods = METHODS + REMAINING_METHODS if args.campaign == "004+006" else METHODS
        campaign_roots = {primary_campaign: BASE / ("compatible_initial_native_20261017_" + primary_campaign)}
        if args.campaign == "004+006":
            campaign_roots["006_remaining12"] = BASE / "compatible_initial_native_20261017_006_remaining12"
        report["source_generations"] = {name: historical_source_archive(directory) for name, directory in campaign_roots.items()}
        report["cases"] = {}
        report["declared_cell_denominator"] = len(scenario_names) * len(methods)
        report["declared_business_endpoint_denominator"] = report["declared_cell_denominator"] * 5
        report["declared_owner_denominator"] = report["declared_cell_denominator"] * 2
        report["failed_or_unknown_cells"] = []
        report["closed_cells_checked"] = 0
        report["closed_owner_bindings_checked"] = 0
        for scenario in scenario_names:
            raws, cases = {}, {}
            for method in methods:
                generation = "006_remaining12" if args.campaign == "004+006" and method in REMAINING_METHODS else primary_campaign
                directory = campaign_roots[generation] / scenario
                try:
                    raws[method], cases[method] = inspect_cell(directory, method)
                    require(len(cases[method]["physical"]["completion"]) == 5, "five-job population not preserved")
                    cases[method]["source_generation"] = generation
                    if method != "incumbent":
                        require("incumbent" in raws, "actual primary-campaign incumbent not available")
                        require(raws[method]["input"] == raws["incumbent"]["input"], "method inputs differ")
                        incumbent = cases["incumbent"]["physical"]["completion"]
                        actual = cases[method]["physical"]["completion"]
                        deltas = {identity: actual[identity] - incumbent[identity] for identity in incumbent}
                        cases[method]["actual_incumbent_reference"] = cases["incumbent"]["raw_path"]
                        cases[method]["observed_completion_delta_from_incumbent"] = deltas
                        cases[method]["zero_degradation_in_this_realization"] = all(delta <= 0.0 for delta in deltas.values())
                        require(cases[method]["zero_degradation_in_this_realization"], "actual per-job degradation")
                        cases[method]["strict_certificate_warning"] = "Observed endpoint dominance is not a current-state or future native-model protection certificate."
                    cases[method]["independent_status"] = "passed_scoped_saved_raw_audit"
                    report["closed_cells_checked"] += 1
                    report["closed_owner_bindings_checked"] += len(cases[method]["owners"])
                except Exception:
                    cases.setdefault(method, {})
                    cases[method].update(independent_status="failed_or_unknown", source_generation=generation,
                                         expected_raw_path=str(directory / (method + ".raw.json.gz")), exception=traceback.format_exc())
                    report["failed_or_unknown_cells"].append(scenario + "/" + method)
            report["cases"][scenario] = cases
            if scenario == "mechanism" and "incumbent" in raws:
                report["old04_vs_campaign_incumbent"] = parity(raws["incumbent"])
        report["endpoint_population_checked"] = report["closed_cells_checked"] * 5
        report["fault_band_T2_passed"] = False
        report["complete_request_100ms_certified"] = False
        optional = BASE / "compatible_initial_native_20261017_004/no_overlap"
        if args.campaign == "003" and (optional / "incumbent.raw.json.gz").exists() and (optional / "incumbent.cell.json").exists():
            raw = read(optional / "incumbent.raw.json.gz")
            cell = read(optional / "incumbent.cell.json")
            require(digest(optional / "incumbent.raw.json.gz") == cell["raw_artifact"]["sha256"], "004 incumbent raw hash mismatch")
            report["optional004_first_no_overlap"] = {"status": "read_only_completed_cell", "cell_status": cell["status"],
                "raw_sha256": digest(optional / "incumbent.raw.json.gz"), "physical": receipt_audit(raw),
                "strict_protected": raw["summary"]["strict_protected"],
                "complete_request_100ms_certified": raw["summary"]["complete_request_100ms_certified"]}
        elif args.campaign == "003":
            report["optional004_first_no_overlap"] = {"status": "not_available_at_read", "directory_exists": optional.exists()}
        report["status"] = "passed_scoped_saved_raw_audit" if not report["failed_or_unknown_cells"] else "failed_or_unknown_cells_retained_in_denominator"
    except Exception:
        report["status"] = "failed"
        report["exception"] = traceback.format_exc()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output), "exception": report.get("exception")}))
    return 0 if report["status"] == "passed_scoped_saved_raw_audit" else 1


if __name__ == "__main__":
    raise SystemExit(main())
