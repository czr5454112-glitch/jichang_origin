"""Independently compare the two authorized HCA time-label repair instances.

Reads native archives only; never invokes Java or either simulation runner.
The route equation includes source and goal dwell, exactly as the corrected
V1 diagnostic. Frozen G31 aggregate observations remain unchanged controls.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "outputs/runtime/hca_time_label_repair_v2_20260906"
OUTPUT = ROOT / "outputs/evidence/hca_time_label_repair_v2_20260906/comparison"
CONTROLS = ROOT / "tmp/hca_time_label_repair_v2_controls_20260906.json"
FREEZE = RUNTIME / "preflight/two_cell_freeze.json"
FREEZE_SHA = "6f3742373bce88f628a673032b8c05b46ef703d95712dde9afe7d31306c6526d"
V1, V2, G31 = "HCA_SEGMENT_IDENTITY_V1", "HCA_TIME_LABEL_REPAIR_V2", "G31_S4_NATIVE_SYSTEM"
MAPS, STATS = ("map2", "nanning"), ("min", "mean", "max")
EQUATION = "expected_goal_T2 = planned_epoch + sum(all path node through times INCLUDING source and goal) + sum(edge lengths / configured speed)"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def root_path(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def ref(path):
    return {"path": Path(path).resolve().relative_to(ROOT).as_posix(), "sha256": sha(path)}


def close(left, right, label):
    if left is None or right is None:
        require(left is right, label)
    else:
        require(math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-7), label)


def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def write(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() or path.read_bytes() == data, "refuse to overwrite different audit: " + str(path))
    path.write_bytes(data)


def native(cell, name):
    manifest = read(cell / "native_archive/manifest.json")
    records = [r for r in manifest["files"] if r["source_name"] == name]
    require(len(records) == 1, "missing/duplicate native archive entry: " + name)
    record = records[0]
    path = (cell / record["path"]).resolve()
    require(path.is_relative_to(cell.resolve()), "native archive path escapes cell")
    compressed = path.read_bytes()
    require(digest(compressed) == record["sha256"], "compressed native SHA differs: " + name)
    data = gzip.decompress(compressed)
    require(digest(data) == record["uncompressed_sha256"], "native SHA differs: " + name)
    if (cell / name).exists():
        require(sha(cell / name) == digest(data), "native/archive bytes differ: " + name)
    return data, {"path": path.relative_to(ROOT).as_posix(), "compressed_sha256": digest(compressed),
                  "uncompressed_sha256": digest(data)}


def freeze_checks(controls):
    require(sha(FREEZE) == FREEZE_SHA, "two-cell pre-run freeze changed")
    freeze = read(FREEZE)
    require(freeze["method"] == V2 and len(freeze["cells"]) == 2, "trial method/count differs")
    require({(c["map"], c["load_factor"], c["seed"]) for c in freeze["cells"]} ==
            {(m, 1.0, 104729) for m in MAPS}, "trial scope exceeds two authorized cells")
    for group in ("protected_files", "frozen_files"):
        for item in freeze[group]:
            require(sha(root_path(item["path"])) == item["sha256"], group + " changed: " + item["path"])
    require(any(root_path(x["path"]).resolve() == CONTROLS.resolve() and x["sha256"] == sha(CONTROLS)
                for x in freeze["frozen_files"]), "controls snapshot was not frozen before runs")
    require(len(controls["controls"]) == 4, "expected four old observations")
    for field in ("source_matrix", "source_manifest", "source_archive_verification", "pre_repair_route_time_formula_audit"):
        item = controls[field]
        require(sha(root_path(item["path"])) == item["sha256"], "old control source changed: " + field)
    return freeze


def audit_native_cell(cell, expected_method):
    status = read(cell / "runner_status.json")
    require(status["method"] == expected_method and status["status"] == "complete" and status["returncode"] == 0,
            "native process incomplete/wrong identity")
    summary = csv_rows(native(cell, "summary.csv")[0])
    require(len(summary) == 1 and summary[0]["method"] == expected_method, "summary identity differs")
    summary = summary[0]
    require(int(summary["fault_event_count"]) == int(summary["repair_event_count"]) == 0, "faults outside formula domain")
    speed = float(summary["speed_mps"])
    require(speed == 2.5, "speed differs")
    map_item = status["inputs"]["map"]
    map_bytes = root_path(map_item["path"]).read_bytes()
    require(digest(map_bytes) == map_item["sha256"], "map bytes changed")
    lines = [line.split() for line in map_bytes.decode("utf-8-sig").splitlines() if line.strip()]
    n = int(lines[0][0])
    dwell = {int(row[0]): float(row[2]) for row in lines[1:n+1]}
    edges = {(int(row[0]), int(row[1])): float(row[2]) for row in lines[1+2*n:]}
    route_data, route_ref = native(cell, "routes.csv")
    routes = csv_rows(route_data)
    ids = [int(r["task_id"]) for r in routes]
    require(len(ids) == len(set(ids)), "duplicate planned execution ID")
    mismatches, examples, gaps = 0, [], []
    for row in routes:
        nodes = list(map(int, row["path"].split(";")))
        require(nodes[0] == int(row["start"]) and nodes[-1] == int(row["goal"]), "path endpoints differ")
        node_time = sum(dwell[node] for node in nodes)
        edge_time = sum(edges[u, v] / speed for u, v in zip(nodes, nodes[1:]))
        expected = node_time + edge_time
        gap = float(row["finish_time"]) - float(row["epoch"]) - expected
        if abs(gap) > 1e-7:
            mismatches += 1
            gaps.append(gap)
            if len(examples) < 3:
                examples.append({"execution_id": int(row["task_id"]), "planned_epoch": float(row["epoch"]),
                                 "recorded_finish_time": float(row["finish_time"]), "route": nodes,
                                 "sum_all_node_through_seconds": node_time, "sum_edge_travel_seconds": edge_time,
                                 "expected_finish_time": float(row["epoch"]) + expected, "excess_seconds": gap})
    mapping_data, mapping_ref = native(cell, "segment_execution_identity.csv")
    mappings = csv_rows(mapping_data)
    by_exec = {int(row["execution_id"]): row for row in mappings}
    require(len(by_exec) == len(mappings) == 43602, "mapping population or unique IDs differ")
    require(set(ids) <= set(by_exec), "route ID has no mapping")
    plan_data, plan_ref = native(cell, "outputstarttime.txt")
    finish_data, finish_ref = native(cell, "output.txt")
    plans, finishes = {}, {}
    for line in plan_data.decode("utf-8-sig").splitlines():
        values = line.split()
        if not values:
            continue
        identifier = int(values[0])
        require(identifier not in plans and identifier in by_exec, "duplicate/unmapped native plan")
        plans[identifier] = float(values[3])
    for line in finish_data.decode("utf-8-sig").splitlines():
        values = line.split()
        if not values:
            continue
        identifier = int(values[0])
        require(identifier not in finishes and identifier in plans, "duplicate/unplanned native completion")
        finishes[identifier] = float(values[1])
        require(finishes[identifier] >= plans[identifier], "completion precedes planning")
    require(set(plans) == set(ids), "native plan/route ID sets differ")
    by_raw = defaultdict(list)
    for identifier, row in by_exec.items():
        by_raw[int(row["raw_task_id"])].append(identifier)
    require(len(by_raw) == 28506, "raw-bag denominator differs")
    completed = [bag for bag, segments in by_raw.items() if all(i in finishes for i in segments)]
    full = len(completed) == len(by_raw)
    metrics = {"completed_raw_bag_count": len(completed), "full_population_complete": full}
    for prefix, start in (("tht_scheduled_release", lambda i: float(by_exec[i]["scheduled_release_seconds"])),
                          ("tht_admission", lambda i: plans[i])):
        values = [sum(finishes[i] - start(i) for i in by_raw[bag]) for bag in completed] if full else []
        for stat, fn in (("min", min), ("mean", statistics.fmean), ("max", max)):
            metrics[f"{prefix}_{stat}_seconds"] = fn(values) if values else None
    normalized = read(cell / "normalized_result.json")
    require(normalized["method"] == expected_method and normalized["status"] == "COMPLETE", "normalized identity/status differs")
    require(normalized["population_audit"]["status"] == "PASS" and normalized["population_audit"]["terminal_accounting_residual"] == 0,
            "terminal accounting did not pass")
    for key, value in metrics.items():
        observed = normalized[key] if key == "full_population_complete" else normalized["metrics"][key]
        close(value, observed, "native-event recomputation differs: " + key)
    return {"cell": cell.relative_to(ROOT).as_posix(), "method": expected_method,
            "source_sha256": status["source_sha256"], "class_sha256": status["class_sha256"],
            "map_sha256": map_item["sha256"], "equation": EQUATION, "tolerance_seconds": 1e-7,
            "planned_route_count": len(routes), "route_formula_mismatch_count": mismatches,
            "max_excess_seconds": max([0.0, *gaps]), "min_excess_seconds": min([0.0, *gaps]),
            "sum_excess_seconds": sum(gaps), "examples": examples, "native_event_metrics": metrics,
            "native_evidence": [route_ref, mapping_ref, plan_ref, finish_ref], "normalized": ref(cell / "normalized_result.json")}


def percentage(numerator, denominator):
    return None if numerator is None or denominator in (None, 0) else numerator / denominator * 100


def comparison_rows(control_lookup, new_results):
    result = []
    for map_name in MAPS:
        old, g31, new = control_lookup[map_name, V1], control_lookup[map_name, G31], new_results[map_name]
        items = [(clock, stat, f"{prefix}_{stat}_seconds", False)
                 for clock, prefix in (("COMMON_CANONICAL_D", "tht_scheduled_release"), ("NATIVE_START", "tht_admission"))
                 for stat in STATS]
        items.append(("FIXED_HORIZON", "TH", "completed_raw_bag_count", True))
        for clock, stat, key, higher in items:
            before = old[key] if higher else old["timing_metrics_seconds"][key]
            reference = g31[key] if higher else g31["timing_metrics_seconds"][key]
            after = new["native_event_metrics"][key]
            available = all(value is not None for value in (before, reference, after))
            orientation = -1 if higher else 1
            old_gap = orientation * (before - reference) if available else None
            new_gap = orientation * (after - reference) if available else None
            old_pct, new_pct = percentage(old_gap, before), percentage(new_gap, after)
            result.append({"map": map_name, "load_factor": 1.0, "seed": 104729, "clock": clock, "statistic": stat,
                           "unit": "raw_bags" if higher else "seconds", "better": "higher" if higher else "lower",
                           "old_hca": before, "repaired_hca": after, "g31_fixed": reference,
                           "repaired_minus_old_hca": after-before if available else None,
                           "hca_improvement_percent": percentage(orientation*(before-after), before) if available else None,
                           "g31_advantage_vs_old_hca_original_units": old_gap,
                           "g31_advantage_vs_repaired_hca_original_units": new_gap,
                           "g31_relative_advantage_vs_old_hca_percent": old_pct,
                           "g31_relative_advantage_vs_repaired_hca_percent": new_pct,
                           "g31_advantage_change_percentage_points": new_pct-old_pct if available and old_pct is not None and new_pct is not None else None})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-controls", action="store_true", help="Read only the two old HCA cells; do not inspect active new cells")
    args = parser.parse_args()
    controls = read(CONTROLS)
    freeze = freeze_checks(controls)
    lookup = {(c["map"], c["method"]): c for c in controls["controls"]}
    old_results = []
    for map_name in MAPS:
        control = lookup[map_name, V1]
        cell = root_path(control["native_record"]["source_path"]).parent
        result = audit_native_cell(cell, V1)
        expected = control["pre_repair_route_time_formula_audit"]
        for field in ("planned_route_count", "route_formula_mismatch_count", "max_excess_seconds", "min_excess_seconds", "sum_excess_seconds"):
            close(result[field], expected[field], "old route formula result differs: " + field)
        for key, value in result["native_event_metrics"].items():
            expected_value = control[key] if key in ("completed_raw_bag_count", "full_population_complete") else control["timing_metrics_seconds"][key]
            close(value, expected_value, "old control timing differs: " + key)
        old_results.append(result)
    if args.check_controls:
        value = {"status": "PASS", "scope": "OLD_TWO_CELL_FORMULA_AND_NATIVE_EVENT_METRIC_RECOMPUTATION_ONLY",
                 "auditor": ref(Path(__file__)), "controls": ref(CONTROLS), "freeze": ref(FREEZE), "cells": old_results,
                 "new_cells_inspected": 0, "simulations_started": 0}
        write(OUTPUT / "control_route_validation.json", value)
        print(json.dumps({"status": "PASS", "old_cells": 2, "new_cells_inspected": 0}))
        return 0
    new_results = {}
    for frozen in freeze["cells"]:
        map_name, cell = frozen["map"], root_path(frozen["output"])
        require(not (cell / ".run_lock").exists() and (cell / "scratch_cleanup.json").exists(), "new native/archive/cleanup not all complete")
        status = read(cell / "runner_status.json")
        require(status["command"] == frozen["command"], "command differs from two-cell freeze")
        require(status["source_sha256"] == freeze["build_source_sha256"] and status["class_sha256"] == freeze["build_class_sha256"], "new source/class differs from freeze")
        old = lookup[map_name, V1]["input_identity"]
        require(status["workload_identity_sha256"] == frozen["identity"]["sha256"] == old["workload_identity_sha256"], "paired identity differs")
        for key, field in (("raw", "input_sha256"), ("canonical", "canonical_sha256"), ("map", "map_sha256")):
            require(status["inputs"][key]["sha256"] == old[field], "new/old input differs: " + key)
        result = audit_native_cell(cell, V2)
        new_results[map_name] = result
    rows = comparison_rows(lookup, new_results)
    formula_pass = all(result["route_formula_mismatch_count"] == 0 for result in new_results.values())
    route_audit = {"schema": "czr005.hca_time_label_repair_v2.route_formula_comparison.v1",
                   "status": "PASS_NO_TOTAL_ROUTE_TIME_MISMATCH_DETECTED" if formula_pass else "FORMULA_MISMATCH_DETECTED",
                   "equation": EQUATION, "tolerance_seconds": 1e-7, "old_cells": old_results,
                   "new_cells": list(new_results.values()), "collision_freedom_claimed": False, "simulations_started": 0}
    write(OUTPUT / "route_time_audit.json", route_audit)
    value = {"schema": "czr005.hca_time_label_repair_v2.two_cell_comparison.v1",
             "status": "TWO_CELL_DIAGNOSTIC_COMPLETE" if formula_pass else "TWO_CELL_DIAGNOSTIC_FORMULA_FAILURE",
             "auditor": ref(Path(__file__)), "controls": ref(CONTROLS), "freeze": ref(FREEZE),
             "old_hca_observations_remain_archived": True, "old_protected_file_count_verified": len(freeze["protected_files"]),
             "frozen_file_count_verified": len(freeze["frozen_files"]), "same_workload_identity": True,
             "new_cells": list(new_results.values()), "rows": rows, "route_audit": ref(OUTPUT / "route_time_audit.json"),
             "limitations": controls["not_claimed"], "bootstrap_performed": False, "simulations_started": 0}
    write(OUTPUT / "comparison.json", value)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    target = OUTPUT / "comparison.csv"
    data = buffer.getvalue().encode("utf-8")
    require(not target.exists() or target.read_bytes() == data, "refuse to overwrite different comparison CSV")
    target.write_bytes(data)
    print(json.dumps({"status": value["status"], "old_cells": 2, "new_cells": 2,
                      "new_route_mismatches": sum(x["route_formula_mismatch_count"] for x in new_results.values()), "comparison_rows": len(rows)}))
    return 0 if formula_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
