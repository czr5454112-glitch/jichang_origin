"""Audit completed repaired Nanning populations without inspecting running outputs.

The audit proves exported identity, lifecycle and counter consistency. Formal
trace=0 files omit current edges, positions and service identities, so they do
not independently prove per-tick collision freedom or absence of repeated
zero-through service starts. Those remain separate Java regression evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external

SOURCE_SHA = "809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f"
CLASS_SHA = "ad828f533bc34abb3527d92f0f476e69412fc14c0024cbf2694bf0f82b382fd0"
RESULT_ROOT = ROOT / "outputs/runtime/cie_external_baseline_zero_through_optimized_v1"
OUTPUT = ROOT / "outputs/evidence/feng_cie_dh_repair_20260905/population_audit.json"
STATES = {"NOT_RELEASED", "AT_LOADING_OR_JUNCTION", "MOVING_ON_EDGE", "STOPPED_ON_EDGE", "COMPLETED"}
FILES = ("runner_status.json", "summary.csv", "bags.csv", "segments.csv", "event_summary.csv")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str) -> float | None:
    if value in {"", "N/A"}:
        return None
    result = float(value)
    require(math.isfinite(result), "non-finite lifecycle time")
    return result


def close(actual: float, expected: float, label: str) -> None:
    require(abs(actual - expected) <= 1e-6, f"{label}: {actual} != {expected}")


def audit_cell(native: Path, status: dict, load: float, seed: int) -> dict:
    require(status.get("schema") == "czr005.feng_paper_env_cie_dh.run.v1"
            and status.get("status") == "complete" and status.get("returncode") == 0,
            "population audit requires a completed native runner")
    hashes = {name: sha(native / name) for name in FILES}
    identity = status["identity"]
    require(identity["method"] == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION", "runner method mismatch")
    require(identity["reconstruction_java_source_aggregate_sha256"] == SOURCE_SHA, "unfrozen source")
    require(identity["compiled_java_class_aggregate_sha256"] == CLASS_SHA, "unfrozen classes")
    require(identity["max_raw_bags"] == 0 and identity["trace_sample_modulo"] == 0,
            "expected full-population trace=0 formal run")
    reference = identity["external_workload_identity"]
    identity_path = Path(reference["path"])
    require(sha(identity_path) == reference["sha256"], "workload identity hash mismatch")
    workload = json.loads(identity_path.read_text(encoding="utf-8"))
    require(workload["map"] == "nanning" and float(workload["load_factor"]) == load
            and workload["seed"] == seed == identity["seed"], "coordinate mismatch")
    require(identity["input_sha256"] == workload["raw_sha256"], "runner input hash mismatch")
    require(identity["map_sha256"] == workload["map_sha256"], "runner map hash mismatch")
    require(sha(Path(workload["raw_path"])) == workload["raw_sha256"], "input bytes drift")
    require(sha(Path(workload["map_path"])) == workload["map_sha256"], "map bytes drift")
    canonical_path = Path(workload["canonical_path"])
    require(sha(canonical_path) == workload["canonical_sha256"], "canonical workload bytes drift")
    expected = defaultdict(dict)
    with canonical_path.open(encoding="utf-8") as handle:
        for line in handle:
            value = json.loads(line)
            segment_id = 1 if value["leg"] == "storage_out" else 0
            key = str(value["task_id"])
            require(segment_id not in expected[key], "duplicate canonical bag/segment identity")
            expected[key][segment_id] = value

    summaries = rows(native / "summary.csv")
    require(len(summaries) == 1, "summary row count is not one")
    summary = summaries[0]
    require(summary["status"] in {"COMPLETE", "HORIZON_REACHED"}, "unexpected terminal status")
    require(summary["input_sha256"] == workload["raw_sha256"]
            and summary["map_sha256"] == workload["map_sha256"], "summary input/map mismatch")
    bags, segments = rows(native / "bags.csv"), rows(native / "segments.csv")
    require(len(bags) == len(expected) == int(summary["raw_bag_count"]) == workload["raw_bag_count"],
            "raw population denominator mismatch")
    require(len(segments) == sum(map(len, expected.values())) == int(summary["segment_count"])
            == workload["segment_count"], "segment denominator mismatch")
    require(len({b["source_raw_bag_id"] for b in bags}) == len(bags)
            and {b["source_raw_bag_id"] for b in bags} == set(expected), "raw source identity lost/duplicated")
    require(len({b["raw_bag_id"] for b in bags}) == len(bags), "duplicate internal raw identity")
    require(len({s["task_id"] for s in segments}) == len(segments), "duplicate internal segment identity")
    require(len({(s["source_raw_bag_id"], s["segment_id"]) for s in segments}) == len(segments),
            "duplicate source bag/segment identity")

    tick = float(summary["tick_seconds"])
    end_tick = int(summary["end_tick"])
    end_seconds = float(summary["simulation_end_seconds"])
    close(end_seconds, end_tick * tick, "end tick/time")
    close(float(summary["horizon_seconds"]), external.FIXED_HORIZON_SECONDS, "formal horizon")
    if summary["status"] == "HORIZON_REACHED":
        close(end_seconds, external.FIXED_HORIZON_SECONDS, "horizon termination")
    by_raw = defaultdict(list)
    states, reasons = Counter(), Counter()
    totals = Counter()
    for segment in segments:
        key, part = segment["source_raw_bag_id"], int(segment["segment_id"])
        require(key in expected and part in expected[key], "foreign bag/segment identity")
        canonical = expected[key][part]
        require(int(segment["segment_count"]) == len(expected[key]), "segment multiplicity mismatch")
        require(int(segment["start"]) == canonical["start"] and int(segment["goal"]) == canonical["goal"],
                "segment OD differs from formal workload")
        close(float(segment["release_seconds"]), float(canonical["pass_time"]), "scheduled release")
        state = segment["status"]
        require(state in STATES, "unknown terminal segment state")
        states[state] += 1
        reasons[segment["last_hold_reason"] or "NONE"] += 1
        by_raw[key].append(segment)
        admission, completion = number(segment["admission_time_seconds"]), number(segment["completion_time_seconds"])
        release_tick = int(segment["release_tick"])
        require(release_tick == math.ceil(float(segment["release_seconds"]) / tick - 1e-9),
                "release tick is not the declared time lattice ceiling")
        moving, stopped, holds = (int(segment[name]) for name in ("moving_ticks", "stopped_ticks", "hold_count"))
        require(0 <= stopped <= holds and moving >= 0, "negative or inconsistent movement/hold counters")
        require((completion is not None) == (state == "COMPLETED"), "completion time/state mismatch")
        require(admission is not None or state in {"NOT_RELEASED", "AT_LOADING_OR_JUNCTION"},
                "edge/completed state without admission")
        if admission is not None:
            require(release_tick * tick <= admission + 1e-6 <= end_seconds + 1e-6, "admission outside lifetime")
            close(admission / tick, round(admission / tick), "admission tick alignment")
        if completion is not None:
            require(admission is not None and admission <= completion <= end_seconds + 1e-6,
                    "completion outside admitted lifetime")
            close(completion / tick, round(completion / tick), "completion tick alignment")
            close(float(segment["diagnostic_first_admission_to_completion_seconds"]), completion - admission,
                  "segment admission latency")
            close(float(segment["table53_scheduled_interval_seconds"]), completion - float(segment["release_seconds"]),
                  "segment scheduled latency")
        else:
            require(number(segment["diagnostic_first_admission_to_completion_seconds"]) is None
                    and number(segment["table53_scheduled_interval_seconds"]) is None,
                    "unfinished segment has completed-only latency")
        if state == "NOT_RELEASED":
            require(release_tick >= end_tick and moving == stopped == holds == 0, "unreleased segment has activity")
        else:
            last_tick = round(completion / tick) if completion is not None else end_tick
            require(moving + holds <= last_tick - release_tick + 1, "more move/hold actions than available ticks")
        if state == "MOVING_ON_EDGE":
            require(segment["last_hold_reason"] == "", "moving state retains a hold reason")
        if state == "STOPPED_ON_EDGE":
            require(stopped > 0 and segment["last_hold_reason"] != "", "stopped state lacks a hold")
        totals.update(moving_ticks=moving, stopped_ticks=stopped, hold_count=holds,
                      entered_segments=int(admission is not None), released_segments=int(state != "NOT_RELEASED"))

    completed_raw = on_time_raw = 0
    for bag in bags:
        key = bag["source_raw_bag_id"]
        parts = by_raw[key]
        require(len(parts) == len(expected[key]) == int(bag["segment_count"]), "raw bag segment coverage mismatch")
        require(all(s["raw_bag_id"] == bag["raw_bag_id"] for s in parts), "internal bag ownership mismatch")
        done = all(s["status"] == "COMPLETED" for s in parts)
        require((bag["complete"] == "true") == done, "raw completion flag differs from its segments")
        completed_raw += done
        if done:
            final = max(float(s["completion_time_seconds"]) for s in parts)
            close(float(bag["final_completion_seconds"]), final, "raw final completion")
            close(float(bag["raw_entry_to_final_seconds"]), final - float(bag["raw_entry_seconds"]), "raw elapsed time")
            for field in ("diagnostic_first_admission_to_completion_seconds", "table53_scheduled_interval_seconds"):
                close(float(bag[field]), sum(float(s[field]) for s in parts), "raw per-segment latency sum")
            on_time = final <= float(bag["deadline_seconds"]) + 1e-9
            require((bag["on_time"] == "true") == on_time, "raw on-time flag mismatch")
            on_time_raw += on_time
        else:
            require(bag["on_time"] == "false" and all(number(bag[field]) is None for field in
                    ("final_completion_seconds", "raw_entry_to_final_seconds", "diagnostic_first_admission_to_completion_seconds",
                     "table53_scheduled_interval_seconds")), "incomplete bag has completed-only metrics")
    require(completed_raw == int(summary["completed_raw_bags"]), "completed raw counter mismatch")
    require(states["COMPLETED"] == int(summary["completed_segments"]), "completed segment counter mismatch")
    require(on_time_raw == int(summary["on_time_raw_bags"]), "on-time raw counter mismatch")
    require((summary["status"] == "COMPLETE") == (states["COMPLETED"] == len(segments)), "terminal status/population mismatch")
    for key, total in totals.items():
        summary_key = "move_commits" if key == "moving_ticks" else key
        require(total == int(summary[summary_key]), f"per-segment counter sum mismatch: {key}")
    events = rows(native / "event_summary.csv")
    require(len({e["event"] for e in events}) == len(events), "duplicate event counter")
    for event in events:
        key = "hold_count" if event["event"] == "holds" else event["event"]
        require(key in summary and int(event["count"]) == int(summary[key]), f"event/summary mismatch: {key}")
    node_holds = sum(int(summary[key]) for key in
                     ("entry_stopped_holds", "entry_moving_holds", "local_fifo_conflict_holds", "no_path_holds"))
    require(totals["hold_count"] - totals["stopped_ticks"] == node_holds, "node/edge hold partition mismatch")
    physical_through_stops = totals["stopped_ticks"] - int(summary["following_footprint_holds"]) - int(summary["junction_through_busy_holds"])
    require(physical_through_stops >= 0, "negative residual positive-through service stops")
    edge_states = states["MOVING_ON_EDGE"] + states["STOPPED_ON_EDGE"]
    active = len(segments) - states["COMPLETED"] - states["NOT_RELEASED"]
    require(edge_states <= int(summary["peak_edge_occupancy"]) and active <= int(summary["peak_active_segments"]),
            "terminal state population exceeds recorded peak")
    formal_latency = load != 2.0 and completed_raw == len(bags)
    require((summary["full_population_timing_eligible"] == "true") == formal_latency, "formal timing gate mismatch")
    if not formal_latency:
        require(all(number(summary[f"diagnostic_first_admission_to_completion_{key}_seconds"]) is None
                    for key in ("mean", "p95", "p99", "max")), "forbidden incomplete/2x summary latency")
    require(all(sha(native / name) == hashes[name] for name in FILES), "native output changed during audit")
    return {"map": "nanning", "load_factor": load, "seed": seed, "status": "PASS",
            "native_terminal_status": summary["status"], "raw_bag_count": len(bags), "segment_count": len(segments),
            "completed_raw_bags": completed_raw, "completed_segments": states["COMPLETED"],
            "incomplete_raw_bags": len(bags) - completed_raw, "terminal_segment_states": dict(sorted(states.items())),
            "terminal_last_hold_reasons": dict(sorted(reasons.items())), "final_edge_state_count_not_position_observation": edge_states,
            "final_active_segment_count": active, "positive_through_stopped_ticks_by_counter_partition": physical_through_stops,
            "counter_sums": dict(totals), "native_sha256": hashes, "workload_identity_sha256": reference["sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--require-complete", action="store_true", help="fail the gate unless all 30 cells are audited")
    args = parser.parse_args()
    audited, skipped, failed = [], [], []
    for load in external.LOAD_FACTORS:
        for seed in external.SEEDS:
            native = external.cell_dir(args.result_root, load, seed, "nanning") / "feng_env_dh"
            status_path = native / "runner_status.json"
            coordinate = {"load_factor": load, "seed": seed}
            if not status_path.is_file():
                skipped.append({**coordinate, "reason": "NO_FINISHED_RUNNER_STATUS_POPULATION_NOT_READ"})
                continue
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("status") != "complete" or status.get("returncode") != 0:
                skipped.append({**coordinate, "reason": "RUNNER_NOT_COMPLETE_POPULATION_NOT_READ"})
                continue
            try:
                audited.append(audit_cell(native, status, load, seed))
            except (ValueError, KeyError, OSError, TypeError) as error:
                failed.append({**coordinate, "error": str(error)})
    result = {"schema": "czr005.feng_repaired_population_audit.v1", "recorded_at": datetime.now(timezone.utc).isoformat(),
              "status": "FAIL" if failed else "PASS" if len(audited) == 30 else "PARTIAL_PASS",
              "audit_script_sha256": sha(Path(__file__)),
              "source_sha256": SOURCE_SHA, "class_sha256": CLASS_SHA, "expected_cells": 30,
              "audited_cells": len(audited), "skipped_cells": skipped, "failures": failed, "cells": audited,
              "evidence_limits": {
                  "terminal_edge_ids_and_positions_exported": False, "node_service_start_counts_exported": False,
                  "independent_per_tick_collision_or_fifo_proof": False,
                  "independent_zero_service_restart_count": None,
                  "long_term_stationary_but_moving_detection": "NOT_DERIVABLE_FROM_TRACE_0_TERMINAL_CSV",
                  "stronger_physics_evidence": "Separate T1-T10/Z1-Z12, real OD and full-population regression; runtime lattice assertions remain enabled.",
                  "source_vs_intermediate_node_split": "AT_LOADING_OR_JUNCTION does not export current_node; no inferred split."}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "audited_cells", "expected_cells", "failures")}))
    return 1 if failed else 2 if args.require_complete and len(audited) != 30 else 0


if __name__ == "__main__":
    raise SystemExit(main())
