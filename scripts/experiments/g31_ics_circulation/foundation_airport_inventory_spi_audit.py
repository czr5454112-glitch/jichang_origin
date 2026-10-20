"""Independent, offline accounting for the frozen inventory/SPI run artifacts.

No simulator, policy selector, fit or callback stream is invoked. Missing
evidence is unknown; failed/unstarted registered cells remain in the roster.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path

from .foundation_airport_batch_patch import digest
from .foundation_airport_behavior_evidence import snapshot_index
from .foundation_airport_pair_dataset import window_cost
from .foundation_airport_service_metrics import (
    backlog_relief, compare_completion_outcomes, physical_progress_intervals,
)

SCHEMA = "g31.inventory_spi_offline_audit.v1"
METHODS = ("R0_current_stock_v1", "C00", "C10", "C01", "C11")
WINDOW = (7200., 59400.)
ACTOR_SOURCE_FILES = tuple("scripts/experiments/g31_ics_circulation/" + name + ".py" for name in (
    "analytic_control", "protocol_control", "foundation_airport_protocol_v2",
    "foundation_airport_inventory_rule", "foundation_airport_batch_patch",
    "foundation_airport_opportunities", "foundation_airport_prospective_control",
    "foundation_airport_pair_ranker", "foundation_airport_strong_rule",
    "foundation_airport_calendar_forecast", "foundation_airport_calendar_prepared",
    "foundation_flight_forecaster", "foundation_flight_forecaster_arrays",
))


def require(ok, reason):
    if not ok:
        raise ValueError("inventory_spi_audit:" + reason)


def sha(path):
    hashed = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def _ref(path):
    path = Path(path)
    return {"path": str(path.resolve()), "sha256": sha(path), "size_bytes": path.stat().st_size}


def _bound(reference):
    require(isinstance(reference, dict) and {"path", "sha256"} <= reference.keys(), "file_binding_required")
    require(sha(reference["path"]) == reference["sha256"], "bound_file_changed:" + reference["path"])
    return read(reference["path"])


def _same_numbers(actual, saved, path="cost"):
    require(type(actual) is type(saved) or
            type(actual) in (int, float) and type(saved) in (int, float), "saved_type:" + path)
    if isinstance(actual, dict):
        require(actual.keys() == saved.keys(), "saved_fields:" + path)
        for key in actual:
            _same_numbers(actual[key], saved[key], path + "." + key)
    elif type(actual) in (int, float):
        require(math.isfinite(actual) and math.isfinite(saved) and
                math.isclose(actual, saved, rel_tol=1e-12, abs_tol=1e-6), "saved_value:" + path)
    else:
        require(actual == saved, "saved_value:" + path)


def _warmup(path):
    if not path.exists():
        return None
    saved = read(path)
    state, prefix = saved["controller_state"], saved["prefix"]
    require(prefix["raw_controller_state_sha256"] == digest(state), "warmup_raw_controller_digest")
    neutral = deepcopy(state)
    allowed = ["stock_return", "stock_return_activate_at", "actual_only_activate_at"]
    require(prefix["only_ignored_config_fields"] == allowed, "warmup_only_registered_config_exclusions")
    for key in allowed:
        neutral["config"].pop(key, None)
    require(prefix["controller_history_sha256"] == digest(neutral)
            and prefix["at"] == 7200.
            and prefix["stage"] == "closed_timestamp_before_refresh_and_any_current_tick_publication",
            "warmup_closed_prepublication_binding")
    return prefix


def _transfers_from_calls(data, calls):
    requests = {r["request_id"]: deepcopy(r) for r in data.get("transfers", [])}
    submitted = {}
    for call in calls:
        if call.get("kind") != "transfer":
            continue
        request = call["request"]
        identity = request["request_id"]
        if identity in submitted:
            require(submitted[identity] == request, "retry_changed_transfer_payload")
            continue
        require(not call.get("retry"), "missing_original_transfer_submission")
        submitted[identity] = deepcopy(request)
        require(identity not in requests, "duplicate_input_and_live_transfer")
        requests[identity] = dict(request, issued_at=call["at"])
    return list(requests.values())


def _physical_diagnostics(data, result, calls, window):
    start, end = window
    receipts = result.get("receipts")
    if not isinstance(receipts, list):
        return {"status": "unknown_missing_receipts", "permanent_deadlock_proven": False}
    failures = [r for r in receipts if r["event"] == "LEG_FAILED"]
    recoveries = [r for r in receipts if r["event"] == "EMPTY_RECOVERY_GRANTED"]
    rejected = [r for r in receipts if r["event"] == "RECOVERY_REJECTED"]
    summary = result.get("native_summary", {})
    invariants = {key: summary.get(key) for key in (
        "reservation_conflicts", "physical_fault_edge_entry_violation_count")}
    invariant_status = ("unknown_missing_counter" if any(v is None for v in invariants.values())
                        else "passed_reported_counters" if all(v == 0 for v in invariants.values())
                        else "violation_reported")
    clock = result.get("physical_clock")
    observed_end = min(end, clock) if type(clock) in (int, float) and math.isfinite(clock) else None
    progress = (physical_progress_intervals(result, start=start, end=observed_end)
                if observed_end is not None and observed_end > start else None)
    output = {
        "status": "receipt_diagnostics_only",
        "global_progress": progress,
        "observed_diagnostic_window": [start, observed_end] if progress is not None else None,
        "unobserved_tail_imputed_as_stall": False,
        "failure_recovery_count_scope": "all saved receipts from initial state to snapshot",
        "failed_legs": len(failures), "failure_reasons": dict(Counter(r["reason"] for r in failures)),
        "failed_empty_legs": sum(not r.get("business_bag_id") for r in failures),
        "empty_recovery_grants": len(recoveries), "recovery_rejections": len(rejected),
        "recovery_rejection_reasons": dict(Counter(r["reason"].rsplit(":", 1)[-1] for r in rejected)),
        "final_quarantined_trays": (sum(t["mode"] == "quarantined" for t in result["trays"])
                                    if isinstance(result.get("trays"), list) else None),
        "native_invariant_counters": invariants, "native_invariant_status": invariant_status,
        "permanent_deadlock_proven": False, "gap_reason_causality": "unknown_without_wait_graph_or_intervention",
        "full_callback_semantics_replayed": False, "fifo_global_correctness": "unknown",
    }
    events = result.get("native_events")
    if isinstance(events, list):
        arbitrations = Counter((r["node"], r["time"]) for r in events
                               if r["event"] == "JUNCTION_ARBITRATION")
        output["observed_duplicate_node_timestamp_arbitrations"] = sum(n-1 for n in arbitrations.values() if n > 1)
        output["native_event_trace_rows"] = len(events)
        output["arbitration_scope"] = "saved trace only; may be truncated; not a full FIFO proof"
    else:
        output["observed_duplicate_node_timestamp_arbitrations"] = None
        output["native_event_trace_rows"] = None
    edge_lengths = {(r[0], r[1]): r[2] for r in data.get("edge_records", [])}
    legs = {r["transport_leg_id"]: r for r in result.get("leg_identities", [])}
    entries, exited = {}, set()
    distances = []
    try:
        require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                    for value in edge_lengths.values()), "finite_nonnegative_edge_lengths")
        require(len(legs) == len(result.get("leg_identities", [])), "unique_leg_identity")
        for row in receipts:
            if row["event"] not in ("EDGE_ENTER", "EDGE_EXIT"):
                continue
            identity = row["traversal_id"]
            if row["event"] == "EDGE_ENTER":
                require(identity not in entries and identity not in exited, "duplicate_traversal_entry")
                entries[identity] = row
                continue
            require(identity in entries and identity not in exited, "exit_without_unique_entry")
            first = entries.pop(identity)
            require(all(first[k] == row[k] for k in ("tray_id", "transport_leg_id", "from", "to"))
                    and first["time"] <= row["time"], "edge_identity_or_time_changed")
            exited.add(identity)
            leg = legs[row["transport_leg_id"]]
            if leg["kind"] == "empty_return" and observed_end is not None and start <= row["time"] <= observed_end:
                distances.append(edge_lengths[(row["from"], row["to"])])
        output.update(empty_completed_edge_distance=math.fsum(distances) if progress is not None else None,
            empty_completed_edge_count=len(distances) if progress is not None else None,
            open_traversals_at_snapshot=len(entries),
            empty_distance_status="paired_actual_entry_exit_and_input_edge_length",
            distance_unit="native input edge length unit",
            distance_window_basis="edge exit in window; partial traversals not imputed")
    except (KeyError, ValueError, TypeError) as exc:
        output.update(empty_completed_edge_distance=None, empty_completed_edge_count=None,
                      empty_distance_status="unknown_invalid_or_missing_traversal_evidence", distance_error=str(exc))
    if calls is None:
        output["lifecycle_capacity_replay"] = {"status": "unknown_missing_client_calls"}
    elif any(v is None for v in invariants.values()):
        output["lifecycle_capacity_replay"] = {"status": "unknown_missing_native_invariant_counters"}
    else:
        # This helper advances no clock and imports no compiled extension.
        from .native_host import audit_result
        try:
            replay = deepcopy(data)
            replay["transfers"] = _transfers_from_calls(data, calls)
            output["lifecycle_capacity_replay"] = audit_result(replay, result)
        except (AssertionError, KeyError, ValueError, TypeError) as exc:
            output["lifecycle_capacity_replay"] = {"status": "failed", "reason": str(exc),
                                                  "exception_type": type(exc).__name__}
    return output


def _control_diagnostics(records, calls, worker):
    counters = worker.get("observed_callback_counts")
    result = {"callback_status_counts": counters,
              "projection_or_model_fallbacks": counters.get("reference_fallback", 0) if isinstance(counters, dict) else None,
              "callback_count_scope": "worker recorded summary; complete callback hash chain not replayed",
              "controller_wall_time_in_physical_J": False,
              "asynchronous_deployment_latency_cost": "unknown"}
    if records is None:
        result.update(controller_ticks=None, owner_decisions=None, measured_controller_ms=None)
    else:
        totals = {"ticks": 0, "owners": 0, "decisions_complete": True, "timings_complete": True}

        def finite_measurement(value):
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                return value
            totals["timings_complete"] = False
            return 0.

        def measurements():
            # Exhaust the iterator: only then are JSON closure/trailing bytes
            # and the gzip trailer checked by the streaming reader.
            for record in records:
                require(isinstance(record, dict), "control_record_object_required")
                totals["ticks"] += 1
                yield finite_measurement(record.get("preparation_compute_ms"))
                decisions = record.get("owner_decisions")
                if not isinstance(decisions, list):
                    totals["decisions_complete"] = False
                    continue
                for decision in decisions:
                    require(isinstance(decision, dict), "owner_decision_object_required")
                    totals["owners"] += 1
                    yield finite_measurement(decision.get("compute_ms"))

        measured = math.fsum(measurements())
        result.update(controller_ticks=totals["ticks"],
            owner_decisions=totals["owners"] if totals["decisions_complete"] else None,
            measured_controller_ms=measured if totals["decisions_complete"] and totals["timings_complete"] else None,
            control_records_read_mode="single pass; iterator exhausted including array/gzip closure",
            timing_scope="recorded preparation plus owner planning/submission; synchronous pause, not physical bag-seconds")
    result["client_call_count"] = len(calls) if calls is not None else None
    result["client_rejected_submission_count"] = (sum(c.get("reply", {}).get("status") == "rejected" for c in calls)
                                                   if calls is not None else None)
    result["client_retry_count"] = sum(bool(c.get("retry")) for c in calls) if calls is not None else None
    return result


def _provenance(plan):
    """Verify available executable/manifest bytes, without executing their code."""
    verified, missing, source_files, actor_hashes = {}, [], None, {}
    actor_missing = list(ACTOR_SOURCE_FILES)
    for key in ("binary", "native_acceptance", "source_bundle"):
        ref = plan.get(key)
        if not isinstance(ref, dict) or not Path(ref.get("path", "")).is_file():
            missing.append(key)
            continue
        require(sha(ref["path"]) == ref["sha256"], "changed_provenance_file:" + key)
        verified[key] = ref
        if key == "native_acceptance":
            accepted = read(ref["path"])
            require(accepted["schema"] == "g31.native030.inventory_spi_accepted_contract.v1"
                    and accepted["status"] in ("passed", "passed_with_retained_fixture_failure"),
                    "native_acceptance_status")
            require(accepted["binary"]["sha256"] == plan["binary"]["sha256"],
                    "native_acceptance_binary_binding")
        if key == "source_bundle":
            source = read(ref["path"])
            require(source["source_manifest_sha256"] == digest(source["files"])
                    == plan["source_manifest_sha256"], "source_manifest_identity")
            source_files = source["files"]
            actor_missing = []
            for relative in ACTOR_SOURCE_FILES:
                path = Path(source["root"])/relative if source.get("root") else None
                if relative not in source_files or path is None or not path.is_file():
                    actor_missing.append(relative)
                    continue
                require(sha(path) == source_files[relative], "changed_actor_source_bytes:" + relative)
                actor_hashes[relative] = source_files[relative]
    return {"status": "bound_files_verified" if not missing else "unknown_missing_provenance_files",
            "verified_files": verified, "missing_files": missing,
            "source_files": source_files,
            "actor_source_hashes": actor_hashes, "actor_source_missing": actor_missing,
            "actor_source_status": "fixed_actor_files_verified" if not actor_missing else "unknown_missing_fixed_actor_files",
            "actor_source_scope": "explicit core file subset only, not a complete dependency closure; "
                                  "campaign wiring and collector behavior are not certified equivalent",
            "source_scope": "bound source manifest plus listed actor bytes; full source closure/build not independently reproduced",
            "native_gates_reexecuted": False}


def audit_run(run_directory, *, expected_population=28506, window=WINDOW):
    directory = Path(run_directory)
    row = {"schema": SCHEMA, "name": directory.name, "directory": str(directory.resolve()),
           "status": "not_started", "audit_status": "unknown_no_closed_receipt",
           "full_window_cost": None, "backlog_relief": None, "strict_nonharm_certified": False,
           "expected_population": expected_population, "window": list(window), "missing_evidence": [],
           "evidence": {}, "errors": []}
    receipt_path = directory/"receipt.json"
    if not receipt_path.exists():
        row["status"] = "not_closed" if (directory/"plan.json").exists() else "not_started"
        return row
    # Check closure before opening run results; a pending run is never audited.
    row["status"] = "unknown_malformed_closed_receipt"
    try:
        receipt = read(receipt_path)
        row["status"] = receipt.get("status", "unknown")
        row["evidence"]["receipt"] = _ref(receipt_path)
        worker = receipt.get("worker") or {}
        require(worker.get("status", row["status"]) == row["status"], "receipt_worker_status_binding")
        plan_path = directory/"plan.json"
        plan = read(plan_path)
        require(receipt.get("plan_sha256") == sha(plan_path), "receipt_plan_binding")
        row.update(method=plan["method"], parent=plan["parent"], parent_seed=plan["parent"]["parent_seed"],
                   binary_sha256=plan["binary"]["sha256"], input_semantic_sha256=plan["input_semantic_sha256"],
                   source_manifest_sha256=plan["source_manifest_sha256"], native_acceptance=plan["native_acceptance"],
                   controller=plan["controller"], wall_seconds=worker.get("wall_seconds"))
        data = _bound(plan["input"])
        require(digest(data) == plan["input_semantic_sha256"], "input_semantic_binding")
        require(len(data["jobs"]) == expected_population, "registered_population")
        row["jobs_digest"], row["initial_trays_digest"] = digest(data["jobs"]), digest(data["trays"])
        row["provenance"] = _provenance(plan)
        row["evidence"].update(plan=_ref(plan_path), input=plan["input"])
        saved = {}
        for key, filename in (("result", "final_result.json.gz"), ("evaluation", "evaluation.json"),
                              ("calls", "client_calls.json.gz"), ("controls", "control_records.json.gz"),
                              ("warmup", "warmup_prefix.json.gz")):
            path = directory/filename
            if path.exists():
                if key == "controls":
                    from .foundation_airport_json_stream import iter_json_array_gz
                    saved[key] = iter_json_array_gz(path)
                else:
                    saved[key] = read(path)
                row["evidence"][key] = _ref(path)
            else:
                saved[key] = None
                row["missing_evidence"].append(filename)
        row["warmup_prefix"] = _warmup(directory/"warmup_prefix.json.gz")
        result, evaluation = saved["result"], saved["evaluation"]
        row["control"] = _control_diagnostics(saved["controls"], saved["calls"], worker)
        if isinstance(result, dict):
            row["physical_clock"] = result.get("physical_clock")
            row["physical"] = _physical_diagnostics(data, result, saved["calls"], window)
        else:
            row["physical_clock"], row["physical"] = None, None
        if row["status"] != "complete":
            require(evaluation is None or evaluation.get("cost") is None, "incomplete_branch_claimed_full_cost")
            row["audit_status"] = "retained_incomplete_no_gain"
            return row
        if result is None or evaluation is None:
            row["audit_status"] = "unknown_missing_completion_evidence"
            return row
        require(plan.get("pair") is None and plan.get("cost_window") == list(window), "full_policy_cost_window_required")
        require(evaluation["status"] == "complete" and evaluation["parent"] == plan["parent"]
                and evaluation["method"] == plan["method"]
                and evaluation["input_semantic_sha256"] == plan["input_semantic_sha256"], "evaluation_binding")
        index = snapshot_index(result, expected_population=expected_population)
        require(index["clock"] == window[1], "exact_common_final_endpoint")
        cost = window_cost(data, result, start=window[0], end=window[1])
        independent = backlog_relief(data["jobs"], index["completions"], start=window[0], end=window[1])
        require(math.isclose(independent["J_bag_seconds"], cost["backlog_integral_bag_seconds"],
                            rel_tol=1e-12, abs_tol=1e-6), "independent_J_recalculation")
        _same_numbers(cost, evaluation["cost"])
        if worker.get("cost") is not None:
            _same_numbers(cost, worker["cost"], "worker.cost")
        require(saved["warmup"] is None or evaluation.get("warmup_prefix") == row["warmup_prefix"],
                "evaluation_warmup_binding")
        row.update(full_window_cost=cost, backlog_relief=independent, audit_status="closed_cost_verified")
    except (AssertionError, KeyError, ValueError, TypeError, OSError, EOFError) as exc:
        row["audit_status"] = "invalid_evidence"
        row["errors"].append(str(exc))
        row["full_window_cost"], row["backlog_relief"] = None, None
    return row


def _compare_rows(reference, candidate):
    result = {"reference": reference["name"], "candidate": candidate["name"],
              "status": "unknown_incomplete_or_unverified", "advantage_bag_seconds": None,
              "completion_direction": None, "strict_nonharm_certified": False}
    provenance = [r.get("provenance", {}) for r in (reference, candidate)]
    files = [p.get("source_files") for p in provenance]
    actors = [p.get("actor_source_hashes") for p in provenance]
    result["source_comparison"] = {
        "full_source_manifest_equal": (reference["source_manifest_sha256"] == candidate["source_manifest_sha256"]
                                      if all("source_manifest_sha256" in r for r in (reference, candidate)) else None),
        "different_source_paths": (sorted(key for key in files[0].keys() | files[1].keys()
                                          if files[0].get(key) != files[1].get(key))
                                   if all(isinstance(f, dict) for f in files) else None),
        "fixed_actor_source_hashes_equal": (actors[0] == actors[1] if all(
            p.get("actor_source_status") == "fixed_actor_files_verified" for p in provenance) else None),
        "actor_source_scope": "fixed core file subset; not full runtime/dependency equivalence",
        "collector_change_semantically_neutral_proven": False,
    }
    if any(r.get("full_window_cost") is None for r in (reference, candidate)):
        return result
    if any(r.get("provenance", {}).get("status") != "bound_files_verified" for r in (reference, candidate)):
        return dict(result, status="unknown_missing_executable_or_manifest_provenance")
    keys = ("parent", "binary_sha256", "input_semantic_sha256", "source_manifest_sha256",
            "native_acceptance", "jobs_digest", "initial_trays_digest", "window")
    mismatch = [k for k in keys if reference.get(k) != candidate.get(k)]
    warmups = [r.get("warmup_prefix") for r in (reference, candidate)]
    if any(w is None for w in warmups):
        return dict(result, status="unknown_missing_common_warmup")
    for key in ("native_state_sha256", "controller_history_sha256", "at", "stage"):
        if warmups[0].get(key) != warmups[1].get(key):
            mismatch.append("warmup." + key)
    if mismatch and mismatch != ["source_manifest_sha256"]:
        return dict(result, status="not_comparable_contract_mismatch", mismatch=mismatch)
    try:
        specs = _bound(reference["evidence"]["input"])["jobs"]
        final = [_bound(r["evidence"]["result"]) for r in (reference, candidate)]
    except (ValueError, OSError) as exc:
        return dict(result, status="invalid_evidence_changed_since_audit", error=str(exc))
    indices = [snapshot_index(value, expected_population=len(specs)) for value in final]
    a, b = reference["full_window_cost"], candidate["full_window_cost"]
    gain = a["backlog_integral_bag_seconds"] - b["backlog_integral_bag_seconds"]
    metrics = dict(advantage_bag_seconds=gain,
        relative_J_gain=None if a["backlog_integral_bag_seconds"] == 0 else gain/a["backlog_integral_bag_seconds"],
        completed_delta=b["completed_by_end"]-a["completed_by_end"],
        on_time_delta=b["on_time_by_end"]-a["on_time_by_end"],
        overdue_unfinished_delta=b["arrived_unfinished_past_deadline"]-a["arrived_unfinished_past_deadline"],
        completion_direction=compare_completion_outcomes(specs, indices[0]["completions"],
            indices[1]["completions"], cutoff=reference["window"][1]),
        warmup_scope="matching saved full native digest and normalized prepublication controller history",
        complete_callback_replay=False, single_action_causal_attribution=False,
        protection_scope="aggregate cost comparison does not certify protection or strict per-job nonharm",
        physical_diagnostics={r["name"]: r.get("physical") for r in (reference, candidate)},
        provenance_status={r["name"]: r.get("provenance", {}).get("status") for r in (reference, candidate)})
    if mismatch:
        return dict(result, status="not_comparable_contract_mismatch", mismatch=mismatch,
            physical_cost_diagnostic={
                "status": "descriptive_same_input_native_warmup_different_source_bundle",
                "reference_J_bag_seconds": a["backlog_integral_bag_seconds"],
                "candidate_J_bag_seconds": b["backlog_integral_bag_seconds"],
                "reference_minus_candidate_J_bag_seconds": gain,
                "completion_direction": metrics["completion_direction"],
                "formal_same_runtime_comparison": False,
                "single_action_causal_attribution": False,
                "physical_diagnostics": metrics["physical_diagnostics"]})
    result.update(status="closed_same_parent_comparison", **metrics)
    return result


def compare_runs(reference_directory, candidate_directory, *, expected_population=28506, window=WINDOW):
    return _compare_rows(audit_run(reference_directory, expected_population=expected_population, window=window),
                         audit_run(candidate_directory, expected_population=expected_population, window=window))


def audit_grid(cycle, specs, *, expected_parent_ids=tuple(range(1301, 1309)), expected_population=28506):
    """All registered five-method cells, including absent/failed branches."""
    expected = {(p, m) for p in expected_parent_ids for m in METHODS}
    actual = [(s["parent_seed"], s["method"]) for s in specs]
    require(len(set(actual)) == len(actual) and set(actual) == expected, "complete_unique_five_method_roster")
    require(len({s["name"] for s in specs}) == len(specs), "unique_run_names")
    require(all(Path(s["name"]).name == s["name"] and s["name"] not in (".", "..")
                and "/" not in s["name"] and "\\" not in s["name"] for s in specs), "local_run_names")
    rows, lookup = [], {}
    for spec in specs:
        row = audit_run(Path(cycle)/"runs"/spec["name"], expected_population=expected_population)
        if "method" in row and (row["method"] != spec["method"] or row["parent_seed"] != spec["parent_seed"]):
            row.update(audit_status="invalid_evidence", full_window_cost=None, backlog_relief=None)
            row["errors"].append("inventory_spi_audit:roster_artifact_binding")
        row.update(registered_method=spec["method"], registered_parent_seed=spec["parent_seed"])
        rows.append(row)
        lookup[(spec["parent_seed"], spec["method"])] = row
    comparisons = []
    for parent in expected_parent_ids:
        for first, second in combinations(METHODS, 2):
            comparisons.append(dict(parent_seed=parent, reference_method=first, candidate_method=second,
                **_compare_rows(lookup[(parent, first)], lookup[(parent, second)])))
    return {"schema": SCHEMA, "registered_parent_count": len(expected_parent_ids),
        "registered_method_count": len(METHODS), "registered_run_count": len(specs),
        "rows": rows, "comparisons": comparisons,
        "statuses": dict(Counter(row["status"] for row in rows)),
        "audit_statuses": dict(Counter(row["audit_status"] for row in rows)),
        "failures_omitted": 0, "missing_cells_imputed_as_zero": False,
        "independent_real_airport_days": 0, "strict_nonharm_certified": False,
        "physical_cost_excludes_synchronously_paused_controller_wall_time": True}
