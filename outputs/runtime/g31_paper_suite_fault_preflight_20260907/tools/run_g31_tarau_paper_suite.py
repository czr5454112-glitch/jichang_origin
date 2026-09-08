#!/usr/bin/env python3
"""New, explicit G31/Tarau paper-suite adapter; never rewrites old runners.

The old ABI supports nominal speed and fault windows, not independent random
physical travel times. Unsupported disturbance specifications fail closed.
Every actual native field is archived, including all returned bag records.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _base in (ROOT, ROOT / "src"):
    if str(_base) not in sys.path:
        sys.path.insert(0, str(_base))

from czr005 import cpp_backend
from scripts.eval import run_cie_component_activation as activation
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval import g4irsf31_map_adapter as adapter
from scripts.eval import run_g4irsf28_service_potential as potentials
from scripts.eval import cie_fixed_denominator_business as business

SPEC_SCHEMA = "czr005.paper_suite.cpp_cell_spec.v1"
RESULT_SCHEMA = "czr005.paper_suite.cpp_cell_result.v1"
NEW_G31_METHOD = "G31_S4_ADVERTISED_FAULT_REPAIR_V1"
METHODS = {
    "G31_S4_NATIVE_SYSTEM": ("S4_queue_aware_rule_only", "M3", "jit_fair_aging_deadline", True),
    NEW_G31_METHOD: ("S4_queue_aware_rule_only", "M3", "jit_fair_aging_deadline", True),
    "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY": (
        "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY", "M1", "jit_fifo", False),
    "G31_S4_ROUTE_ONLY_M1_CONTROL": ("S4_queue_aware_rule_only", "M1", "jit_fifo", True),
}


class SuiteError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _encode(value: Any) -> Any:
    """Reversible strict-JSON encoding; never silently turns infinity into NA."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"__paper_suite_nonfinite_float__": repr(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"__paper_suite_nonfinite_float__"}:
            return float(value["__paper_suite_nonfinite_float__"])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def _bytes(value: Any) -> bytes:
    return (json.dumps(_encode(value), sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SuiteError(f"expected JSON object: {path}")
    return value


def _bound_file(path: Any, expected: Any) -> Path:
    resolved = Path(str(path)).resolve(strict=True)
    if not isinstance(expected, str) or len(expected) != 64 or sha256(resolved) != expected:
        raise SuiteError(f"file SHA mismatch: {resolved}")
    return resolved


def _edge_pairs(value: Any, label: str) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise SuiteError(f"{label} must be an explicit edge list")
    result = []
    for pair in value:
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) for v in pair)):
            raise SuiteError(f"{label} must contain integer directed pairs")
        result.append((pair[0], pair[1]))
    if len(result) != len(set(result)):
        raise SuiteError(f"{label} contains duplicate edges")
    return result


def _atomic_json(path: Path, value: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(_bytes(value))
    os.replace(tmp, path)


def _output_root(path: Path) -> Path:
    result = path.resolve()
    relative = result.relative_to(ROOT.resolve())
    parts = relative.parts
    allowed = (len(parts) >= 3 and parts[:2] == ("outputs", "runtime")
               and "paper_suite" in parts[2]) or (len(parts) >= 2 and parts[0] in {"tmp", "build"}
                                                  and "paper_suite" in parts[1])
    if not allowed:
        raise SuiteError("output must be a new paper_suite runtime or workspace QA directory")
    return result


@dataclass(frozen=True)
class Prepared:
    spec: dict[str, Any]
    identity: dict[str, Any]
    rows: tuple[dict[str, Any], ...]
    request: dict[str, Any]
    provenance: dict[str, Any]


def prepare_spec(spec: Mapping[str, Any]) -> Prepared:
    if spec.get("schema") != SPEC_SCHEMA or spec.get("method") not in METHODS:
        raise SuiteError("unknown spec schema or explicit method identity")
    # Accept the compact orchestrator contract; freeze the resolved full spec.
    spec = dict(spec)
    identity_path = _bound_file(spec["workload_identity_path"], spec["workload_identity_sha256"])
    identity = _json(identity_path)
    external.audit_cell(identity_path)
    spec.setdefault("map", identity["map"])
    spec.setdefault("load_factor", identity["load_factor"])
    spec.setdefault("fixed_horizon_seconds", spec.get("horizon_seconds"))
    spec.setdefault("nominal_speed_mps", spec.get("speed_mps"))
    for key in ("map", "seed", "load_factor", "fixed_horizon_seconds"):
        if spec.get(key) != identity.get(key):
            raise SuiteError(f"workload/spec {key} mismatch")
    if float(spec["load_factor"]) not in (1.0, 2.0):
        raise SuiteError("paper suite permits only 1x / 2x")
    if spec.get("timing_policy") != "full_population_only":
        raise SuiteError("new suite requires full_population_only; old unconditional 2x NA does not carry over")
    scenario = dict(spec.get("scenario", {}))
    scenario.setdefault("family", spec.get("family"))
    spec["scenario"] = scenario
    family = scenario.get("family")
    if family not in {"base", "fault", "all_day_fault"}:
        raise SuiteError("old C++ ABI has no independent physical speed disturbance; no fallback allowed")
    if scenario.get("physical_disturbance") not in (None, {"kind": "none"}):
        raise SuiteError("physical disturbance requires a separately frozen native ABI")
    nominal = float(spec["nominal_speed_mps"])
    if nominal not in (1.5, 2.5, 3.0):
        raise SuiteError("unregistered nominal speed")
    binary = _bound_file(spec["binary_path"], spec["binary_sha256"])
    protocol = _bound_file(spec["protocol_path"], spec["protocol_sha256"])
    profile_path = _bound_file(spec["map_profile_path"], spec["map_profile_sha256"])
    profile = activation._profile_for_map(str(spec["map"]), profile_path)
    if profile.source_path.resolve() != profile_path:
        raise SuiteError("requested map-profile path is not the profile actually used")
    rows = activation._read_jsonl(Path(identity["canonical_path"]))
    trace = spec.get("trace", {})
    for field in ("decision_limit", "event_limit"):
        if isinstance(trace.get(field), bool) or not isinstance(trace.get(field), int):
            raise SuiteError("explicit integer trace limits are required")
    request, potential = adapter.build_s4_request(
        profile, rows, binary=binary, scenario=str(spec["cell_id"]),
        max_events=activation.MAX_EVENTS,
        max_simulation_time=float(spec["fixed_horizon_seconds"]),
        edge_speed_mps=nominal, summary_only=False,
        trace_limit=trace["decision_limit"], event_trace_limit=trace["event_limit"],
        enable_s4_local_potential_descent_guard=METHODS[str(spec["method"])][3],
        enable_s4_direct_neighbor_merge_calendar_visibility=METHODS[str(spec["method"])][3],
        complete_on_goal_arrival=True,
    )
    scorer, merge, timing, _ = METHODS[str(spec["method"])]
    request.update(scorer_mode=scorer, merge_grant_rule=merge, merge_grant_timing_mode=timing)
    if spec["method"] == NEW_G31_METHOD:
        request["enable_s4_advertised_fault_potential_repair"] = True
    # This diagnostic native ABI explicitly supports S4 only.
    request["enable_cie_component_activation"] = scorer == "S4_queue_aware_rule_only"
    fault_edges: list[tuple[int, int]] = []
    mapping_identity = None
    if family in {"fault", "all_day_fault"}:
        if scenario.get("information_contract") != "KNOWN_SURVIVING_TOPOLOGY_NO_SOURCE_PREFILTER":
            raise SuiteError("main fault cells require the shared known-surviving-topology contract")
        mapping_path = _bound_file(spec["fault_mapping_path"], spec["fault_mapping_sha256"])
        fault_edges = _edge_pairs(scenario.get("fault_edges"), "scenario.fault_edges")
        declared_failed = _edge_pairs(spec.get("failed_edges"), "failed_edges")
        initial_failed = _edge_pairs(spec.get("initial_failed_edges"), "initial_failed_edges")
        affected = _edge_pairs(spec.get("affected_edges"), "affected_edges")
        if set(declared_failed) != set(fault_edges):
            raise SuiteError("failed_edges and scenario.fault_edges differ")
        edges = {(int(e[0]), int(e[1])) for e in request["edge_records"]}
        if not fault_edges or len(fault_edges) != len(set(fault_edges)) or not set(fault_edges) <= edges:
            raise SuiteError("fault edges must be distinct directed edges of this actual map")
        if (not initial_failed or not set(initial_failed) <= set(fault_edges)
                or set(fault_edges) != set(affected) or not set(affected) <= edges):
            raise SuiteError("all methods must disable the whole shared closure, separately preserving initial failures")
        if spec.get("affected_count") != len(affected):
            raise SuiteError("affected_count differs from explicit propagated edge list")
        index, line_ids = spec.get("scenario_index"), spec.get("paper_line_ids")
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= 16:
            raise SuiteError("registered scenario_index must be 1..16")
        if not isinstance(line_ids, list) or not line_ids or any(type(v) is not int or not 1 <= v <= 8 for v in line_ids):
            raise SuiteError("paper_line_ids must identify the registered lines, not map edge ordinals")
        if spec["map"] == "map2":
            mapping = _json(mapping_path)
            matches = [r for r in mapping.get("fault_scenarios", []) if r.get("scenario_index") == index]
            if len(matches) != 1:
                raise SuiteError("map2 source mapping does not uniquely identify the scenario")
            match = matches[0]
            if (line_ids != match["paper_line_ids"]
                    or set(initial_failed) != set(_edge_pairs(match["initial_edges"], "mapping initial_edges"))
                    or set(affected) != set(_edge_pairs(match["map2_affected_edges"], "mapping affected_edges"))):
                raise SuiteError("map2 actual fault/propagation differs from the bound source mapping")
        mapping_identity = {"path": str(mapping_path), "sha256": sha256(mapping_path),
                            "scenario_index": index, "paper_line_ids": line_ids,
                            "initial_failed_edges": initial_failed,
                            "initial_failed_edge_count": len(initial_failed),
                            "failed_edges": fault_edges, "affected_edges": affected,
                            "affected_count": len(affected),
                            "disabled_edge_count": len(fault_edges),
                            "physical_fault_edges": fault_edges,
                            "propagation_authority": "COMMON_EXTERNAL_PROTOCOL_NOT_NATIVE_ALGORITHM",
                            "initial_failures_and_disabled_closure_separately_reported": True}
        # No source cohort removal and no fabricated native rejection rows.
        request["fault_windows"] = [(u, v, 0.0, float(spec["fixed_horizon_seconds"]) + 1.0, 0.0, False)
                                    for u, v in fault_edges]
        if (scenario["information_contract"] == "KNOWN_SURVIVING_TOPOLOGY_NO_SOURCE_PREFILTER"
                and spec["method"] != NEW_G31_METHOD):
            surviving = [e for e in request["edge_records"] if (int(e[0]), int(e[1])) not in fault_edges]
            request["heuristic_time"], potential = potentials.service_aware_potential(
                request["node_records"], surviving,
                minimum_service_seconds=float(request["minimum_service_seconds"]))
    elif scenario.get("fault_edges"):
        raise SuiteError("base cell cannot carry fault edges")
    manifest = {
        "spec_sha256": hashlib.sha256(_bytes(spec)).hexdigest(),
        "request_sha256": hashlib.sha256(_bytes(request)).hexdigest(),
        "runner_path": str(Path(__file__).resolve()), "runner_sha256": sha256(Path(__file__)),
        "workload_identity_path": str(identity_path),
        "workload_identity_sha256": sha256(identity_path),
        "raw_sha256": identity["raw_sha256"], "canonical_sha256": identity["canonical_sha256"],
        "map_sha256": identity["map_sha256"], "profile_path": str(profile_path),
        "profile_sha256": sha256(profile_path), "binary_path": str(binary), "binary_sha256": sha256(binary),
        "protocol_path": str(protocol), "protocol_sha256": sha256(protocol),
        "potential_contract": potential, "fault_edges": fault_edges,
        "fault_mapping": mapping_identity,
        "source_prefilter": False, "synthetic_native_rows": False,
        "fidelity": "G31_WITH_ADVERTISED_FAULT_ONLY_GLOBAL_POTENTIAL_REPAIR" if spec["method"] == NEW_G31_METHOD
                    else "CURRENT_G31_SYSTEM" if spec["method"] == "G31_S4_NATIVE_SYSTEM"
                    else "ROUTE_ADAPTATION_OR_CONTROL_NOT_ORIGINAL_END_TO_END_REPRODUCTION",
        "fault_potential_contract": "ORIGINAL_GRAPH_INITIAL_H_NATIVE_REPAIR_AFTER_DELIVERED_NOTIFICATION"
                    if spec["method"] == NEW_G31_METHOD else "NO_NEW_NATIVE_POTENTIAL_REPAIR",
        "python": sys.version, "python_executable": sys.executable,
    }
    return Prepared(dict(spec), identity, rows, request, manifest)


def audit_payload(prepared: Prepared, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Pure, portable population/goal/clock check; does not launch C++."""
    summary, bags = payload.get("summary"), payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise SuiteError("native payload lacks summary/bags")
    expected = {str(row["segment_id"]): row for row in prepared.rows}
    observed = [str(row.get("segment_id", "")) for row in bags]
    if len(observed) != len(set(observed)) or set(observed) != set(expected):
        raise SuiteError("native segment set is missing, duplicate, or foreign")
    joined = {str(row["segment_id"]): row for row in bags}
    runtime_ids = [int(row["runtime_bag_id"]) for row in bags]
    if len(set(runtime_ids)) != len(runtime_ids):
        raise SuiteError("native runtime bag IDs are not unique")
    by_raw: dict[int, list[str]] = defaultdict(list)
    completed = 0
    horizon = float(prepared.spec["fixed_horizon_seconds"])
    for sid, can in expected.items():
        bag = joined[sid]
        for field in ("task_id", "start", "goal"):
            if int(bag[field]) != int(can[field]):
                raise SuiteError(f"native {field} differs from canonical for {sid}")
        if not math.isclose(float(bag["release_time"]), float(can["pass_time"]), abs_tol=1e-7, rel_tol=0):
            raise SuiteError(f"native release changed canonical scheduled D: {sid}")
        if not isinstance(bag["completed"], bool):
            raise SuiteError("completed flag must be boolean")
        if bag["completed"]:
            finish, admitted = float(bag["finish_time"]), float(bag["admitted_time"])
            if (int(bag["final_node"]) != int(can["goal"]) or not math.isfinite(finish)
                    or not math.isfinite(admitted) or finish < admitted or admitted < float(can["pass_time"]) - 1e-7
                    or finish > horizon + 1e-7):
                raise SuiteError(f"completed goal/clock violation: {sid}")
            completed += 1
        by_raw[int(can["task_id"])].append(sid)
    # The native full-protocol flag also requires an untruncated debug log.
    # Keep that flag exactly as observed; execution integrity is independently
    # computable from the native lifetime counters and live-state audits.
    active_integrity = (summary.get("merge_grant_conservation_holds") is True
                        and summary.get("merge_grant_active_bijection_holds") is True
                        and summary.get("merge_grant_runtime_owned_capability") is True
                        and summary.get("merge_grant_exact_slot_no_future_shift") is True
                        and summary.get("merge_grant_final_active_unconsumed") == 0
                        and summary.get("merge_grant_outstanding_request_count") == 0)
    dropped = summary.get("merge_grant_lifecycle_dropped_count")
    lifecycle_complete = isinstance(dropped, int) and not isinstance(dropped, bool) and dropped == 0
    compensation = (summary.get("merge_grant_post_commit_rollback_count") is not None
                    and summary.get("merge_grant_post_commit_rollback_count") == summary.get("merge_grant_queue_capacity_block_count"))
    gates = {
        "segment_population": len(bags) == prepared.identity["segment_count"],
        "raw_population": len(by_raw) == prepared.identity["raw_bag_count"],
        "summary_completed": int(summary.get("completed_count", -1)) == completed,
        "terminal_partition": completed + int(summary.get("failed_count", -1)) == len(bags),
        "binary_sha": summary.get("loaded_cpp_binary_sha256") == prepared.spec["binary_sha256"],
        "fixed_horizon": float(summary.get("declared_max_simulation_time", -1)) == horizon,
        "event_budget": int(summary.get("declared_max_events", -1)) == int(prepared.request["max_events"]),
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "fault_event_count": int(summary.get("fault_event_count", -1)) == sum(
            float(window[2]) <= horizon for window in prepared.request.get("fault_windows", [])),
        "repair_event_count": int(summary.get("repair_event_count", -1)) == sum(
            float(window[3]) <= horizon for window in prepared.request.get("fault_windows", [])),
        "scorer_echo": summary.get("scorer_mode_echo") == prepared.request["scorer_mode"],
        "merge_rule_echo": summary.get("merge_grant_rule") == prepared.request["merge_grant_rule"],
        "merge_timing_echo": summary.get("merge_grant_timing_mode") == prepared.request["merge_grant_timing_mode"],
        "reservation_conflicts_zero": summary.get("reservation_conflicts") == 0,
        "fault_entry_violations_zero": summary.get("physical_fault_edge_entry_violation_count") == 0,
        "merge_conservation": summary.get("merge_grant_conservation_holds") is True,
        "merge_active_bijection": summary.get("merge_grant_active_bijection_holds") is True,
        "native_safe_execution": summary.get("safe_execution_pass") is True,
        "native_merge_active_state": active_integrity,
        "native_active_state_echo": summary.get("merge_grant_active_state_integrity_pass") is active_integrity,
        "native_post_commit_compensation": compensation,
        "native_post_commit_compensation_echo": summary.get("merge_grant_post_commit_capacity_compensation_pass") is compensation,
        "native_protocol_echo": summary.get("merge_grant_protocol_integrity_pass") is (active_integrity and lifecycle_complete),
        "lifecycle_drop_counter": isinstance(dropped, int) and not isinstance(dropped, bool) and dropped >= 0,
        "lifecycle_complete_echo": summary.get("merge_grant_lifecycle_complete") is lifecycle_complete,
        "lifecycle_truncation_echo": summary.get("merge_grant_lifecycle_telemetry_truncated") is (not lifecycle_complete),
        "lifecycle_stored_count": summary.get("merge_grant_lifecycle_stored_count") == len(payload.get("merge_grant_lifecycle", [])),
    }
    if prepared.spec.get("method") == NEW_G31_METHOD:
        known_edges = len({(int(w[0]), int(w[1])) for w in prepared.request.get("fault_windows", [])})
        gates.update(fault_repair_enabled=summary.get("s4_advertised_fault_potential_repair_enabled") is True,
                     fault_repair_active_edges=summary.get("s4_fault_potential_active_advertised_edge_count") == known_edges,
                     fault_repair_no_restoration=summary.get("s4_fault_potential_restore_original_count") == 0,
                     fault_repair_rebuild_activity=(summary.get("s4_fault_potential_rebuild_count", -1) > 0 if known_edges
                                                   else summary.get("s4_fault_potential_rebuild_count") == 0))
    if not all(gates.values()):
        raise SuiteError(f"native integrity failures: {[k for k, v in gates.items() if not v]}")
    raw_rows = []
    for raw_id, ids in sorted(by_raw.items()):
        done = all(joined[sid]["completed"] for sid in ids)
        std = min(float(expected[sid]["std"]) for sid in ids)
        finish = max(float(joined[sid]["finish_time"]) for sid in ids) if done else None
        raw_rows.append({"task_id": raw_id, "segment_count": len(ids), "complete": done,
                         "std_seconds": std, "finish_seconds": finish,
                         "success_std": done and finish <= std,
                         "success_paper_literal": done and finish <= std - 2700.0,
                         "tht_common_scheduled_D_seconds": math.fsum(float(joined[sid]["finish_time"]) - float(expected[sid]["pass_time"])
                                                                      for sid in ids) if done else None,
                         "tht_native_admitted_seconds": math.fsum(float(joined[sid]["finish_time"]) - float(joined[sid]["admitted_time"])
                                                                    for sid in ids) if done else None})
    complete_raw = sum(row["complete"] for row in raw_rows)
    full = complete_raw == len(raw_rows)
    timing_eligible = full
    return {
        "status": "PASS", "gates": gates,
        "full_population_complete": full, "raw_bag_count": len(raw_rows), "segment_count": len(bags),
        "completed_segment_count": completed, "unfinished_segment_count": len(bags) - completed,
        "completed_raw_bag_count": complete_raw, "unfinished_raw_bag_count": len(raw_rows) - complete_raw,
        "TH_definition": "complete_raw_bags_at_fixed_horizon", "fixed_horizon_seconds": horizon,
        "completion_rate": complete_raw / len(raw_rows), "timing_eligible": timing_eligible,
        "success_rate_std": sum(row["success_std"] for row in raw_rows) / len(raw_rows),
        "success_rate_paper_literal": sum(row["success_paper_literal"] for row in raw_rows) / len(raw_rows),
        "success_deadlines": {"std": "raw vendor STD", "paper_literal": "raw vendor STD minus 2700 seconds",
                              "canonical_D_changed": False},
        "primary_timing_definition": "raw_bag_sum_of_segment_finish_minus_common_canonical_scheduled_D",
        "primary_timing": business._describe([row["tht_common_scheduled_D_seconds"] for row in raw_rows]) if timing_eligible else None,
        "native_timing_definition": "raw_bag_sum_of_segment_finish_minus_native_admitted_time",
        "native_timing": business._describe([row["tht_native_admitted_seconds"] for row in raw_rows]) if timing_eligible else None,
        "raw_rows": raw_rows,
        "trace": {"decision_trace_truncated": summary.get("decision_trace_truncated"),
                  "event_trace_truncated": summary.get("event_trace_truncated"),
                  "native_full_protocol_integrity_pass": summary.get("merge_grant_protocol_integrity_pass"),
                  "native_active_state_integrity_pass": summary.get("merge_grant_active_state_integrity_pass"),
                  "merge_grant_lifecycle_complete": lifecycle_complete,
                  "merge_grant_lifecycle_dropped_count": dropped,
                  "merge_grant_lifecycle_stored_count": summary.get("merge_grant_lifecycle_stored_count"),
                  "full_lifecycle_trace_proof_claimed": lifecycle_complete,
                  "short_history_is_full_path": False,
                  "all_returned_native_fields_preserved": True},
        "scope": "identity_goal_terminal_accounting_and_clocks; not continuous_geometry_or_all_tick_collision_proof",
    }


def _gzip_json(path: Path, value: Any) -> dict[str, Any]:
    content = _bytes(value)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(content)
    return {"path": path.name, "sha256": sha256(path), "content_sha256": hashlib.sha256(content).hexdigest(),
            "bytes": path.stat().st_size, "content_bytes": len(content)}


def run_spec(spec_path: Path, output_dir: Path) -> dict[str, Any]:
    prepared = prepare_spec(_json(spec_path.resolve(strict=True)))
    output = _output_root(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "normalized_result.json"
    if result_path.exists():
        return load_completed(output, prepared=prepared)
    with (output / "run.lock").open("x", encoding="utf-8") as lock:
        lock.write(str(os.getpid()))
    try:
        if (output / "native_payload.json.gz").exists():
            raise SuiteError("native evidence already exists without accepted result; inspect without overwriting")
        _atomic_json(output / "run_spec.json", prepared.spec)
        _atomic_json(output / "run_identity.json", prepared.provenance)
        _gzip_json(output / "request.json.gz", prepared.request)
        _atomic_json(output / "runner_status.json", {"status": "RUNNING", "pid": os.getpid(),
                                                   "spec_sha256": prepared.provenance["spec_sha256"]})
        started = time.perf_counter()
        payload = cpp_backend.g4irsf11_event_runtime_from_records(**prepared.request)
        elapsed = time.perf_counter() - started
        # Archive before validation so failed runs retain original observations.
        archives = {"native_payload": _gzip_json(output / "native_payload.json.gz", payload)}
        if isinstance(payload.get("bags"), list):
            archives["bags"] = _gzip_json(output / "bags.json.gz", payload["bags"])
        _atomic_json(output / "native_archive.json", {"encoding": "strict_JSON_with_reversible_nonfinite_float_tags", "files": archives})
        audit = audit_payload(prepared, payload)
        archives["raw_population"] = _gzip_json(output / "raw_population.json.gz", audit.pop("raw_rows"))
        result = {"schema": RESULT_SCHEMA, "status": "COMPLETE", "method": prepared.spec["method"],
                  "map": prepared.spec["map"], "load_factor": prepared.spec["load_factor"],
                  "seed": prepared.spec["seed"],
                  "fixed_horizon_seconds": prepared.spec["fixed_horizon_seconds"],
                  "workload_identity_sha256": prepared.provenance["workload_identity_sha256"],
                  "spec": prepared.spec, "provenance": prepared.provenance, "population_audit": audit,
                  "native_wall_seconds": elapsed, "archives": archives}
        _atomic_json(result_path, result)
        _atomic_json(output / "runner_status.json", {"status": "COMPLETE", "native_wall_seconds": elapsed,
                                                   "normalized_result_sha256": sha256(result_path)})
        return result
    except Exception as exc:
        _atomic_json(output / "runner_status.json", {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        raise
    finally:
        (output / "run.lock").unlink()


def load_completed(output_dir: Path, *, prepared: Prepared | None = None) -> dict[str, Any]:
    result = _json(output_dir / "normalized_result.json")
    if result.get("schema") != RESULT_SCHEMA or result.get("status") != "COMPLETE":
        raise SuiteError("result is not an accepted paper-suite terminal run")
    prepared = prepared or prepare_spec(result["spec"])
    if result["provenance"] != prepared.provenance:
        raise SuiteError("completed result provenance no longer matches actual inputs/runner")
    for entry in result["archives"].values():
        path = output_dir / entry["path"]
        if path.parent.resolve() != output_dir.resolve() or sha256(path) != entry["sha256"]:
            raise SuiteError("native archive path/SHA mismatch")
        with gzip.open(path, "rb") as stream:
            content = stream.read()
        if hashlib.sha256(content).hexdigest() != entry["content_sha256"]:
            raise SuiteError("native archive content SHA mismatch")
    with gzip.open(output_dir / "native_payload.json.gz", "rt", encoding="utf-8") as stream:
        payload = _decode(json.load(stream))
    audit = audit_payload(prepared, payload)
    audit.pop("raw_rows")
    if audit != result["population_audit"]:
        raise SuiteError("portable native population/metric audit differs from normalized result")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "verify"))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "verify":
        result = load_completed(args.output)
        print(json.dumps({"status": "PASS", "population_audit": result["population_audit"]}))
    elif args.command == "run":
        if args.spec is None:
            parser.error("--spec is required")
        result = run_spec(args.spec, args.output)
        print(json.dumps({"status": result["status"], "population_audit": result["population_audit"]}))
    else:
        if args.spec is None:
            parser.error("--spec is required")
        prepared = prepare_spec(_json(args.spec))
        output = _output_root(args.output)
        output.mkdir(parents=True, exist_ok=True)
        _atomic_json(output / "prepared_identity.json", prepared.provenance)
        _gzip_json(output / "prepared_request.json.gz", prepared.request)
        print(json.dumps({"status": "PREPARED_NOT_EXECUTED", "identity": prepared.provenance}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
