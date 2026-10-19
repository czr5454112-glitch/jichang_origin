"""Recheck the original input and bounded physical witnesses without a full-day run."""
from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import asdict
import gzip
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .audit_original_carrier_bound import analyze
from .native_host import audit_result, load_native, prepare_input, tiny_cycle
from .original_workload import (
    DEFAULT_MAP, DEFAULT_RAW, ROOT, ProxyContract, build_input, digest,
    json_digest, source_map, static_diagnostics, verify_source_map,
)

BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
SAVED_INPUT = BASE / "full_stream_native024_001/full1x/input.json.gz"
BUILD_RECEIPT = BASE / "native027_build_001/receipt.json"
BINARY = ROOT / "build_lt_session_027/python/czr005_circulation.cp311-win_amd64.pyd"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def path_witness(edges, source, target, positive_only):
    adjacency = {}
    for edge in edges:
        if not positive_only or edge["capacity"] > 0:
            adjacency.setdefault(edge["from"], []).append(edge["to"])
    parents = {source: None}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for following in sorted(adjacency.get(node, [])):
            if following not in parents:
                parents[following] = node
                queue.append(following)
    path = []
    if target in parents:
        cursor = target
        while cursor is not None:
            path.append(cursor)
            cursor = parents[cursor]
    return list(reversed(path)), sorted(parents)


def static_review():
    saved = json.loads(gzip.decompress(SAVED_INPUT.read_bytes()))
    contract = ProxyContract(**saved["model_contract"])
    rebuilt, manifest, crosswalk = build_input(
        scale=1, contract=contract,
        horizon=saved["options"]["max_simulation_time"],
        max_events=saved["options"]["max_events"],
        trace_limit=saved["options"]["trace_limit"],
        scorer=saved["options"]["scorer_mode"],
    )
    common = sorted(set(rebuilt) & set(saved))
    differences = [key for key in common if json_digest(rebuilt[key]) != json_digest(saved[key])]
    if differences:
        raise ValueError("original projection differs from saved input: " + repr(differences))
    profile = json.loads(DEFAULT_MAP.read_text(encoding="utf-8"))
    source_check = verify_source_map(profile, source_map.default_source_dir())
    zero_edges = [edge for edge in profile["edges"] if edge["pallet_capacity"] == 0]
    source_edges = [asdict(edge) for workbook in source_map.load_source_dir(source_map.default_source_dir())
                    for edge in workbook.edges if edge.pallet_capacity == 0]
    bound = analyze(saved)
    diagnostic = static_diagnostics(saved)
    first_bad = min(
        (row for loader in bound["loaders"] for row in loader["jobs_in_native_fifo_order"] if not row["reachable"]),
        key=lambda row: (row["arrival"], row["business_bag_id"]),
    )
    job = next(row for row in saved["jobs"] if row["business_bag_id"] == first_bad["business_bag_id"])
    identity = next(row for row in crosswalk if row["business_bag_id"] == job["business_bag_id"])
    raw_line = DEFAULT_RAW.read_text(encoding="utf-8-sig").splitlines()[identity["original_source_line"] - 1]
    stages = []
    for key in first_bad["mandatory_stages"]:
        witness = bound["stages"][key]
        topological_path, _ = path_witness(saved["edge_contracts"], witness["source"], witness["target"], False)
        reached = set(witness["complete_reachable_set"])
        cut = [edge for edge in saved["edge_contracts"] if edge["from"] in reached and edge["to"] not in reached]
        if not witness["reachable"]:
            assert cut and all(edge["capacity"] == 0 for edge in cut)
        stages.append({**witness, "path_if_capacity_ignored_diagnostic_only": topological_path,
                       "outgoing_cut": cut, "target_outside_reachable_set": witness["target"] not in reached})
    assert (diagnostic["capacity_positive_path_unreachable"], bound["completion_upper_bound"],
            bound["zero_unreachable_load_prefix_bound"]) == (4001, 371, 39)
    return {
        "status": "closed_under_existing_research_contract_field_semantics_unconfirmed",
        "source_hashes": {str(path.relative_to(ROOT)): digest(path) for path in (DEFAULT_RAW, DEFAULT_MAP, SAVED_INPUT)},
        "source_map_verification": source_check,
        "reconstruction": {"common_fields_equal": common, "common_field_differences": differences,
                           "saved_only_fields": sorted(set(saved) - set(rebuilt)),
                           "rebuilt_only_fields": sorted(set(rebuilt) - set(saved)),
                           "rebuilt_input_sha256": json_digest(rebuilt), "saved_semantic_sha256": json_digest(saved)},
        "manifest": manifest,
        "capacity_trace": {"source_zero_rows": source_edges, "profile_zero_edges": zero_edges,
                           "edge_count": len(profile["edges"]),
                           "all_capacities_equal_floor_length_over_2": all(
                               edge["pallet_capacity"] == math.floor(edge["length"] / 2) for edge in profile["edges"]),
                           "native_zero_contract": [edge for edge in saved["edge_contracts"] if edge["capacity"] == 0],
                           "capacity_interpretation": "native simultaneous traversals; zero means closed; field interpretation unknown",
                           "entry_headway_seconds": contract.entry_headway_seconds,
                           "exit_headway_contract": "no separate exit-headway field; traversal exit uses source travel time"},
        "business_roles_ebs": profile["business_roles"]["ebs"],
        "storage_source_node": next(row for row in profile["nodes"] if row["location"] == job["storage_node"]),
        "initial_trays": saved["trays"],
        "initial_count_by_node": dict(sorted(Counter(row["node"] for row in saved["trays"]).items())),
        "static_diagnostics": diagnostic,
        "carrier_bound": {key: value for key, value in bound.items() if key not in {"loaders", "stages", "dp_tables"}},
        "earliest_unreachable_task": {"projected_job": job, "source_crosswalk": identity,
                                      "original_source_line_text": raw_line, "fifo_record": first_bad, "stages": stages},
        "all_original_jobs_possible": False,
        "condition": "unchanged capacity-zero-closed, mandatory-stage, FIFO, on-carrier and 22-tray research contract",
        "field_system_feasibility": "unknown_pending_one_physical_contract_question_table",
    }


def closed_edge_micro():
    return prepare_input({
        "schema": "g31.circulation.input.v1",
        "model_scope": "synthetic two-node necessary counterexample; not a modified Nanning experiment",
        "node_records": [(0, 1, 0.001, 0, 0, [1]), (1, 2, 0.001, 0, 0, [])],
        "edge_records": [(0, 1, 0.6, 2.0)],
        "node_contracts": [{"node": 0, "zone": "A", "capacity": 1}, {"node": 1, "zone": "B", "capacity": 1}],
        "edge_contracts": [{"from": 0, "to": 1, "capacity": 0, "entry_headway": 1.0}],
        "trays": [{"tray_id": "T0", "node": 0}],
        "jobs": [{"business_bag_id": identity, "origin": 0, "destination": 1,
                  "arrival": arrival, "deadline": 40.0, "storage_node": -1,
                  "load_seconds": 0.0, "unload_seconds": 0.0, "hold_seconds": 0.0}
                 for identity, arrival in (("blocked-first", 0.0), ("waiting-second", 0.1))],
        "transfers": [], "faults": [],
        "options": {"max_simulation_time": 40.0, "max_events": 10000, "trace_limit": 10000},
    })


def native_review(output):
    build = json.loads(BUILD_RECEIPT.read_text(encoding="utf-8"))
    binary_sha = digest(BINARY)
    assert build["binary_sha256"][str(BINARY)] == binary_sha
    source_mismatches = [name for name, expected in build["source_after"].items() if digest(ROOT / name) != expected]
    assert not source_mismatches, source_mismatches
    executable = BINARY.parent.parent / "test_circulation_runtime.exe"
    assert digest(executable) == build["binary_sha256"][str(executable)]
    started = time.perf_counter()
    checked = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60)
    executable_result = {"returncode": checked.returncode, "stdout": checked.stdout, "stderr": checked.stderr,
                         "wall_seconds": time.perf_counter() - started, "sha256": digest(executable)}
    assert checked.returncode == 0, executable_result
    native = load_native(BINARY)
    cycle = tiny_cycle()
    cycle["options"].update(max_simulation_time=40.0, max_events=10000, trace_limit=10000)
    cases = {}
    for name, data in (("same_tray_two_services", cycle), ("zero_capacity_fifo_counterexample", closed_edge_micro())):
        started = time.perf_counter()
        result = native.run(data)
        elapsed = time.perf_counter() - started
        audit = audit_result(data, result)
        raw_path = output / (name + ".json")
        save(raw_path, {"input": data, "result": result, "receipt_audit": audit, "wall_seconds": elapsed})
        cases[name] = {"raw_file": raw_path.name, "raw_sha256": digest(raw_path), "receipt_audit": audit,
                       "jobs": result["jobs"], "trays": result["trays"], "transfers": result["transfers"],
                       "receipt_count": len(result["receipts"]), "wall_seconds": elapsed}
        if name == "same_tray_two_services":
            assert all(row["status"] == "completed" and row["deadline_met"] for row in result["jobs"])
            assert {row["tray"] for row in result["jobs"]} == {0}
            assert result["jobs"][1]["loaded_at"] >= result["transfers"][0]["received_at"] > result["jobs"][0]["completed_at"]
            assert result["trays"][0]["mode"] == "empty"
        else:
            assert not any(row["event"] in {"EDGE_ENTER", "UNLOAD_COMPLETE"} for row in result["receipts"])
            assert all(row["completed_at"] < 0 for row in result["jobs"])
            assert result["jobs"][0]["loaded_at"] >= 0 and result["jobs"][1]["loaded_at"] < 0
            assert len(result["trays"]) == 1 and result["trays"][0]["node"] == 0
        cases[name]["business_assertions"] = "passed"
    return {"status": "passed_bounded_native_witnesses", "binary": str(BINARY), "binary_sha256": binary_sha,
            "build_receipt": str(BUILD_RECEIPT), "build_receipt_sha256": digest(BUILD_RECEIPT),
            "current_source_mismatches_from_frozen_build": source_mismatches,
            "existing_cpp_test": executable_result, "cases": cases,
            "native_python_micro_calls": 2, "full_day_native_calls": 0,
            "counterexample_proof": "One mandatory directed edge has zero native traversal capacity. No admissible traversal exists at any time; finite observation alone is not the impossibility proof."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "g31.physical_contract_review.20261017.v1", "status": "running",
              "command": sys.argv, "python": sys.version, "script_sha256": digest(Path(__file__)),
              "executed": [], "not_executed": ["original full-day rerun", "2x bound extrapolation",
                  "field-semantic correction", "off-carrier EBS", "zero-capacity reinterpretation"]}
    try:
        report["static"] = static_review()
        report["executed"].append("original1x source reconstruction and static proof")
        save(args.output / "physical_contract_evidence.json", report)
        report["native"] = native_review(args.output)
        report["executed"].append("existing C++ test and two bounded native physical witnesses")
        report["status"] = "evidence_closed_field_contract_pending"
    except Exception:
        report["status"] = "failed"
        report["exception"] = traceback.format_exc()
    save(args.output / "physical_contract_evidence.json", report)
    print(json.dumps({"status": report["status"], "output": str(args.output), "exception": report.get("exception")}))
    return int(report["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
