"""Read-only diagnosis of an existing DH horizon result; never invokes Java."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import hashlib
import inspect
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_dh_paper_suite as runner

CELL = ROOT / "outputs/runtime/feng_paper_suite_20260907/cells/b_nanning_2x_v2p5_s104729_q00_dh"
OUT = ROOT / "tmp/dh_na_horizon_diagnosis_20260907.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value):
    if value in ("", "N/A", "NaN", "nan", None):
        return None
    value = float(value)
    assert math.isfinite(value), "unexpected nonfinite numeric token"
    return value


def main():
    protected = [CELL / name for name in ("segments.csv", "bags.csv", "summary.csv", "event_summary.csv",
        "trace.csv", "runner_status.json", "build_identity.json", "stdout.txt", "stderr.txt")]
    before = {str(path): sha(path) for path in protected}
    status = runner.read(CELL / "runner_status.json")
    assert status["status"] == "NATIVE_COMPLETE" and status["returncode"] == 0
    spec_path = Path(status["spec_path"])
    assert sha(spec_path) == status["spec_sha256"]
    spec = runner.read(spec_path)
    identity_path, identity = runner.external._identity_payload(Path(spec["workload_identity_path"]))
    assert sha(identity_path) == spec["workload_identity_sha256"]
    summary = runner.csv_rows(CELL / "summary.csv")[0]
    events = {row["event"]: int(row["count"]) for row in runner.csv_rows(CELL / "event_summary.csv")}
    assert summary["status"] == "HORIZON_REACHED" and float(summary["simulation_end_seconds"]) == 98259
    assert summary["map_sha256"] == sha(identity["map_path"])
    assert summary["input_sha256"] == sha(identity["raw_path"])
    build = runner.read(CELL / "build_identity.json")
    assert build == runner.read(runner.BUILD / "build_identity.json")
    assert build["source_files"] == runner.file_set(runner.SOURCE, "*.java")
    assert build["class_files"] == runner.file_set(runner.BUILD, "*.class")

    # Execute an isolated copy of the existing pure normalizer with just the
    # missing-token parser corrected. Original module globals/files remain untouched.
    namespace = {"csv_rows": runner.csv_rows, "require": runner.require, "Path": Path, "json": json,
                 "defaultdict": defaultdict, "math": math, "finite_or_none": number}
    exec(inspect.getsource(runner.normalize), namespace)
    derived = namespace["normalize"](identity, CELL)
    raw_derived = {row["task_id"]: row for row in derived.pop("bags")}
    segments = runner.csv_rows(CELL / "segments.csv")
    raw = runner.csv_rows(CELL / "bags.csv")
    counts = Counter(row["status"] for row in segments)
    assert len({row["task_id"] for row in segments}) == len(segments)
    assert all(int(row["task_id"]) == 2 * int(row["source_raw_bag_id"]) + int(row["segment_id"]) for row in segments)
    assert len(raw) == len({int(row["source_raw_bag_id"]) for row in raw}) == len(raw_derived)
    for row in raw:
        item = raw_derived[int(row["source_raw_bag_id"])]
        assert int(row["segment_count"]) == item["segment_count"]
        assert (row["complete"] == "true") == item["complete"]
        assert (row["on_time"] == "true") == item["on_time_std"]
        assert number(row["final_completion_seconds"]) == item["finish_seconds"]
    metrics = derived["metrics"]
    assert metrics["completed_raw_bag_count"] == int(summary["completed_raw_bags"])
    assert metrics["completed_segment_count"] == int(summary["completed_segments"]) == counts["COMPLETED"]
    assert int(summary["raw_bag_count"]) == identity["raw_bag_count"] == len(raw)
    assert int(summary["segment_count"]) == identity["segment_count"] == len(segments)
    assert sum(row["on_time_std"] for row in raw_derived.values()) == int(summary["on_time_raw_bags"])
    admitted = sum(number(row["admission_time_seconds"]) is not None for row in segments)
    assert admitted == int(summary["entered_segments"]) == events["entered_segments"]
    assert events["released_segments"] == int(summary["released_segments"]) == len(segments)
    assert not derived["full_population_complete"]
    assert all(value is None for key, value in metrics.items() if key.startswith("tht_"))

    # Same edge-ID order and cell-length rule as FengDhEdgeLattice.readLegacyMap.
    lines = Path(identity["map_path"]).read_text().splitlines()
    n = int(lines[0].split()[0])
    edges = [line.split() for line in lines[1 + 2*n:] if line.strip()]
    occupancy = defaultdict(list)
    for row in segments:
        edge, pos = int(row["current_edge_id"]), int(row["position_cell"])
        if edge >= 0:
            assert row["status"] in ("MOVING_ON_EDGE", "STOPPED_ON_EDGE")
            assert 0 <= edge < len(edges)
            cell_count = max(1, math.ceil(float(edges[edge][2]) / (.2*spec["speed_mps"]) - 1e-12))
            assert 0 <= pos < cell_count
            occupancy[edge].append(pos)
        else:
            assert pos == -1
        if row["status"] == "COMPLETED":
            assert edge == -1 and int(row["final_node"]) == int(row["goal"])
    for positions in occupancy.values():
        positions.sort()
        assert all(b-a >= int(summary["footprint_cells"]) for a,b in zip(positions,positions[1:]))
    missing = [(index+2, row) for index,row in enumerate(segments) if row["completion_time_seconds"] == "N/A"]
    assert len(missing) == len(segments) - counts["COMPLETED"]
    first_line, first = missing[0]
    try:
        runner.finite_or_none(first["completion_time_seconds"])
    except ValueError as error:
        parser_failure = str(error)
    else:
        parser_failure = "CURRENT_RUNNER_ALREADY_CHANGED; historical traceback remains primary evidence"
    after = {str(path): sha(path) for path in protected}
    assert before == after
    result = {"schema": "czr005.dh_na_horizon_readonly_diagnosis.v1", "status": "PASS",
        "classification": "POSTPROCESSING_MISSING_VALUE_TOKEN_PARSE_FAILURE",
        "native_simulations_invoked": 0, "protected_native_bytes_unchanged": True, "native_files": before,
        "native_status": summary["status"], "native_java_returncode": status["returncode"],
        "generating_runner_sha256": status["runner_sha256"], "inspected_runner_sha256": sha(runner.__file__),
        "native_build_identity_sha256": sha(CELL / "build_identity.json"), "spec_sha256": sha(spec_path),
        "workload_identity_sha256": sha(identity_path), "state_counts": dict(counts),
        "completion_NA_count": len(missing), "admission_NA_count": len(segments)-admitted,
        "first_failing_csv_line": first_line, "first_failing_native_row": first, "parser_error": parser_failure,
        "original_normalizer_with_only_local_NA_parser_change": derived,
        "raw_csv_matches_all_recomputed_bags": True, "summary_and_event_counters_match": True,
        "terminal_edge_occupancy_rows": sum(map(len,occupancy.values())), "terminal_edge_ranges_and_footprints_valid": True,
        "scope": "Exact canonical ID/OD/D, completed goals/causal clocks, all raw rows/summary/events, terminal lattice bounds and headways. No per-tick trace; not a new continuous-physics proof or validation of reconstruction assumptions.",
        "coverage_gap": "The V6 preflight script invokes native mechanism tests and V5/V6 first-200 comparisons but never invokes the Python normalizer on an incomplete native CSV containing N/A."}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ("status","classification","state_counts","completion_NA_count","admission_NA_count","first_failing_csv_line","terminal_edge_occupancy_rows")},ensure_ascii=False))
    print(str(OUT))


if __name__ == "__main__":
    main()
