#!/usr/bin/env python3
"""Bounded real-C++ capability and adapter checks; no campaign population runs."""
from __future__ import annotations
import argparse
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for _base in (ROOT, ROOT / "src"):
    if str(_base) not in sys.path:
        sys.path.insert(0, str(_base))
from scripts.eval import run_g31_tarau_paper_suite as suite

BINARY = ROOT / "build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd"
BINARY_SHA = "b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5"
METHODS = ("G31_S4_NATIVE_SYSTEM", "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY")


def prepared(map_name: str, method: str, speed: float = 2.5, *, mid_fault: bool = False) -> suite.Prepared:
    profile = suite.activation._profile_for_map(map_name, suite.activation.DEFAULT_NANNING_PROFILE)
    # Each probe starts on an upstream edge before notification. The next edge
    # has a directed alternative on the actual map. Cases are fixed here, not
    # selected from relative algorithm performance.
    start, goal, blocked = (0, 47, (6, 12)) if map_name == "map2" else (0, 16, (1, 2))
    notification_time = 1.0 if map_name == "map2" else 2.0
    rows = ({"segment_id": "1001:direct", "task_id": 1001, "start": start, "goal": goal,
             "pass_time": 0.0, "std": 5000.0, "original_entry_time": 0.0},)
    score, merge, timing, guard = suite.METHODS[method]
    request, _ = suite.adapter.build_s4_request(
        profile, rows, binary=BINARY, scenario="SYNTHETIC_PAPER_SUITE_BOUNDED_NATIVE_QA",
        max_events=100_000, max_simulation_time=1000.0,
        trace_limit=20_000, event_trace_limit=20_000, summary_only=False,
        edge_speed_mps=speed, enable_s4_local_potential_descent_guard=guard,
        enable_s4_direct_neighbor_merge_calendar_visibility=guard, complete_on_goal_arrival=True)
    request.update(scorer_mode=score, merge_grant_rule=merge, merge_grant_timing_mode=timing,
                   enable_cie_component_activation=score == "S4_queue_aware_rule_only")
    if mid_fault:
        request["fault_windows"] = [(*blocked, notification_time, 1001.0, 0.0, False)]
    spec = {"method": method, "fixed_horizon_seconds": 1000.0, "binary_sha256": BINARY_SHA,
            "load_factor": 2.0, "timing_policy": "full_population_only"}
    return suite.Prepared(spec, {"raw_bag_count": 1, "segment_count": 1}, rows, request, {
        "scope": "SYNTHETIC_ONE_BAG_REAL_MAP_REAL_FROZEN_CPP_NOT_FULL_POPULATION",
        "map": map_name, "profile_sha256": suite.sha256(profile.source_path),
        "source": start, "goal": goal, "blocked_edge": blocked if mid_fault else None,
        "fault_time": notification_time if mid_fault else None,
        "notification_time": notification_time if mid_fault else None,
        "physical_event_known_in_planner_before_fault": False,
        "surviving_potential_precomputed": False,
    })


def run(output: Path) -> dict:
    if suite.sha256(BINARY) != BINARY_SHA:
        raise RuntimeError("frozen b00 binary mismatch")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "verification.json").exists():
        raise RuntimeError("bounded evidence already exists; do not overwrite")
    records = []
    originals = {}
    for method in METHODS:
        for speed in (1.5, 2.5, 3.0):
            p = prepared("map2", method, speed)
            payload = suite.cpp_backend.g4irsf11_event_runtime_from_records(**p.request)
            audit = suite.audit_payload(p, payload)
            assert audit["full_population_complete"] and audit["timing_eligible"]
            assert audit["primary_timing"] is not None  # new full-complete 2x rule
            name = f"base_{method}_{speed:g}"
            archive = suite._gzip_json(output / f"{name}.json.gz", payload)
            request_archive = suite._gzip_json(output / f"{name}.request.json.gz", p.request)
            records.append({"name": name, "status": "PASS", "archive": archive,
                            "request_archive": request_archive,
                            "audit": audit, "request_sha256": hashlib.sha256(suite._bytes(p.request)).hexdigest()})
            if speed == 2.5:
                originals[method] = (p, payload)
    for method, (p, payload) in originals.items():
        # Existing C++ result is the control; mutate only returned observations
        # to test the actual independent Python validator, not C++ routing.
        wrong = copy.deepcopy(payload)
        wrong["bags"][0]["final_node"] = 49
        try:
            suite.audit_payload(p, wrong)
        except suite.SuiteError:
            pass
        else:
            raise AssertionError("wrong destination accepted")
        missing = copy.deepcopy(payload)
        missing["bags"] = []
        try:
            suite.audit_payload(p, missing)
        except suite.SuiteError:
            pass
        else:
            raise AssertionError("missing segment accepted")
        # Verify collecting trace records does not change this real native bag.
        no_trace = dict(p.request, trace_limit=0, event_trace_limit=0)
        quiet = suite.cpp_backend.g4irsf11_event_runtime_from_records(**no_trace)
        assert quiet["bags"] == payload["bags"]
    for map_name in ("map2", "nanning"):
        for method in METHODS:
            p = prepared(map_name, method, mid_fault=True)
            payload = suite.cpp_backend.g4irsf11_event_runtime_from_records(**p.request)
            audit = suite.audit_payload(p, payload)
            name = f"mid_fault_{map_name}_{method}"
            archive = suite._gzip_json(output / f"{name}.json.gz", payload)
            request_archive = suite._gzip_json(output / f"{name}.request.json.gz", p.request)
            decisions = payload["decisions"]
            events = payload["fault_events"]
            notification_time = p.provenance["notification_time"]
            records.append({"name": name, "status": "PASS_ACCOUNTING_NOT_REQUIRED_COMPLETION",
                            "contract": p.provenance, "archive": archive, "request_archive": request_archive,
                            "audit": audit,
                            "request_sha256": hashlib.sha256(suite._bytes(p.request)).hexdigest(),
                            "decisions_before_notification": [r for r in decisions if float(r["event_time"]) < notification_time],
                            "decisions_after_notification": [r for r in decisions if float(r["event_time"]) >= notification_time],
                            "fault_event_count": len(events), "fault_event_examples": events[:32],
                            "fault_event_phase_counts": dict(Counter(row["phase"] for row in events)),
                            "unfinished_bags": [r for r in payload["bags"] if not r["completed"]],
                            "selected_native_summary": {k: v for k, v in payload["summary"].items()
                                                        if any(t in k for t in ("fault", "repair", "reroute", "loop_count"))}})
    strict = suite._decode(json.loads(suite._bytes({"x": float("inf"), "y": float("-inf")})))
    assert strict == {"x": float("inf"), "y": float("-inf")}
    result = {"schema": "czr005.paper_suite.cpp_bounded_capability.v1", "status": "PASS",
              "binary_path": str(BINARY.resolve()), "binary_sha256": BINARY_SHA,
              "adapter_sha256": suite.sha256(Path(suite.__file__)), "harness_sha256": suite.sha256(Path(__file__)),
              "checks": {"six_real_native_base_cells": True, "wrong_goal_rejected": True,
                         "missing_segment_rejected": True, "trace_on_off_bag_equivalence": True,
                         "full_complete_2x_timing_available": True, "nonfinite_encoding_roundtrip": True},
              "mid_fault_scope": "two fixed single-bag real-map fixtures per method, no campaign inference",
              "records": records}
    suite._atomic_json(output / "verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({"status": result["status"], "checks": result["checks"],
                      "records": [{"name": r["name"], "complete": r["audit"]["full_population_complete"]} for r in result["records"]]}))
