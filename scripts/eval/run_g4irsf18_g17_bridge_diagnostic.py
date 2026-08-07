#!/usr/bin/env python3
"""Probe whether the frozen G17 scorer can serve as a research-only bridge.

The diagnostic intentionally keeps the published G17 model and gate read-only.
It first runs the protected 144/512 prefixes with the requested native binary,
then checks whether that binary exposes the append-only G17 source-policy ABI.
An optional research closed loop is limited to the 144 prefix and uses an
in-memory gate copy; it cannot change production authorization.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BINARY = Path(
    r"C:\PROGRAMING\czr005\build_g17_agent_pybind_latest\python"
    r"\czr005_cpp.cp311-win_amd64.pyd"
)
PAIRWISE_MODEL = ROOT / "artifacts/models/g4irsf17_i1_pairwise_linear.json"
SELECTIVE_GATE = ROOT / "artifacts/gates/g4irsf17_i1_selective_gate.json"
DEFAULT_OUTPUT = ROOT / "outputs/tables/g4irsf18_g17_bridge_diagnostic.json"


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile needs at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _binding_bags(rows: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            str(row["segment_id"]),
            int(row["task_id"]),
            float(row["pass_time"]),
            float(row["std"]),
            int(row["start"]),
            int(row["goal"]),
            str(row.get("source", f"node_{int(row['start'])}")),
        )
        for row in rows
    ]


def _hard_safety(summary: Mapping[str, Any], segments: int) -> dict[str, Any]:
    observed = {
        "requested_count": summary.get("requested_count"),
        "completed_count": summary.get("completed_count"),
        "failed_count": summary.get("failed_count"),
        "event_count": summary.get("event_count"),
        "reservation_conflicts": summary.get("reservation_conflicts"),
        "physical_fault_edge_entry_violation_count": summary.get(
            "physical_fault_edge_entry_violation_count"
        ),
        "runtime_full_astar_calls": summary.get("runtime_full_astar_calls"),
        "global_reservation_scan_count": summary.get(
            "global_reservation_scan_count"
        ),
        "unresolved_deadlock_count": summary.get("unresolved_deadlock_count"),
    }
    checks = {
        "all_segments_complete": (
            observed["requested_count"] == segments
            and observed["completed_count"] == segments
            and observed["failed_count"] == 0
        ),
        "no_reservation_conflict": observed["reservation_conflicts"] == 0,
        "no_physical_fault_entry": (
            observed["physical_fault_edge_entry_violation_count"] == 0
        ),
        "no_full_astar": observed["runtime_full_astar_calls"] == 0,
        "no_global_scan": observed["global_reservation_scan_count"] == 0,
        "no_unresolved_deadlock": observed["unresolved_deadlock_count"] == 0,
        "within_event_cap": (
            isinstance(observed["event_count"], int)
            and observed["event_count"] <= 20_000_000
        ),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "observed": observed,
    }


def _policy_shadow_summary(
    payload: Mapping[str, Any], selector: Mapping[str, Any]
) -> dict[str, Any]:
    rows = payload.get("g4irsf17_source_policy_decisions", [])
    if not isinstance(rows, list):
        raise TypeError("native policy decisions must be a list")

    def passes(row: Mapping[str, Any]) -> bool:
        return bool(
            row.get("proposed_candidate_index")
            != row.get("baseline_candidate_index")
            and row.get("out_of_distribution") is False
            and row.get("supervisor_authorized") is True
            and float(row.get("benefit_probability_lcb", -math.inf))
            >= float(selector["benefit_probability_lcb_min"])
            and float(row.get("harmful_probability_ucb", math.inf))
            < float(selector["harm_probability_ucb_max"])
            and float(row.get("utility_lcb_seconds", -math.inf))
            > float(selector["utility_lcb_min_seconds"])
            and float(row.get("calibration_ece", math.inf))
            <= float(selector["calibration_ece_max"])
        )

    summary = payload.get("summary", {})
    return {
        "decision_count": len(rows),
        "reason_counts": dict(
            sorted(Counter(str(row.get("reason")) for row in rows).items())
        ),
        "alternative_proposal_count": sum(
            row.get("proposed_candidate_index")
            != row.get("baseline_candidate_index")
            for row in rows
        ),
        "selector_pass_ignoring_artifact_and_runtime_authorization_count": sum(
            passes(row) for row in rows
        ),
        "action_mutation_count": sum(bool(row.get("activated")) for row in rows),
        "ood_count": sum(
            bool(row.get("out_of_distribution")) for row in rows
        ),
        "native_counters": {
            key: value
            for key, value in summary.items()
            if str(key).startswith("g4irsf17_source_policy")
        },
    }


def _run_prefix(
    *,
    segments: int,
    binary: Path,
    policy_mode: str = "off",
    policy_artifact: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from czr005 import cpp_backend
    from scripts.eval import g4irsf12_reproducible_harness as g12
    from scripts.eval.g4irsf11_fixed_map import (
        assert_canonical_map,
        canonical_graph_records,
    )
    from scripts.eval.g4irsf14_opportunity_census import (
        FROZEN_RUNTIME_CONTROLS,
        MODEL_PATH,
    )

    prefix = g12.load_input_prefix(segments, root=ROOT)
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=_binding_bags(prefix.rows),
        fault_windows=[],
        scenario=f"g4irsf18_g17_bridge_{policy_mode}_{segments}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        scorer_model_path=(ROOT / MODEL_PATH).resolve(strict=True),
        search_path=binary.parent,
        g4irsf16_supervisor_mode="off",
        enable_g4irsf17_source_wait_telemetry=True,
        g4irsf17_source_wait_trace_limit=200_000,
    )
    if policy_mode != "off":
        request.update(
            g4irsf17_source_policy_mode=policy_mode,
            g4irsf17_source_policy_artifact=dict(policy_artifact or {}),
            g4irsf17_source_policy_trace_limit=200_000,
        )
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    summary = payload["summary"]
    aggregate = g12.aggregate_raw_bag_timings(prefix.rows, payload["bags"])
    completed = [row for row in aggregate if row["complete"]]
    tth = [float(row["original_entry_time_tth_seconds"]) for row in completed]
    source_wait = [float(row["source_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    result = {
        "segments": segments,
        "input_protocol": "protected_first_n_file_order",
        "tth_denominator": "original_entry_time_tth",
        "task_count": len(aggregate),
        "complete_task_count": len(completed),
        "mean_tth_seconds": statistics.fmean(tth) if tth else None,
        "p95_tth_seconds": _quantile(tth, 0.95) if tth else None,
        "p99_tth_seconds": _quantile(tth, 0.99) if tth else None,
        "mean_source_wait_seconds": (
            statistics.fmean(source_wait) if source_wait else None
        ),
        "mean_network_seconds": statistics.fmean(network) if network else None,
        "cpu_seconds": cpu_seconds,
        "wall_seconds": wall_seconds,
        "source_wait_telemetry": {
            "interval_total_count": summary.get(
                "g4irsf17_source_wait_interval_total_count"
            ),
            "interval_stored_count": summary.get(
                "g4irsf17_source_wait_interval_stored_count"
            ),
            "interval_dropped_count": summary.get(
                "g4irsf17_source_wait_interval_dropped_count"
            ),
            "wait_seconds": summary.get("g4irsf17_source_wait_seconds"),
            "wait_bag_seconds": summary.get(
                "g4irsf17_source_wait_bag_seconds"
            ),
        },
        "hard_safety": _hard_safety(summary, segments),
    }
    return result, dict(payload)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--segments", type=int, nargs="+", default=[144, 512])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--research-closed-loop",
        action="store_true",
        help=(
            "If the ABI exists and shadow/control safety passes, run only the "
            "144 prefix with an ephemeral relaxed gate copy."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    binary = args.binary.resolve(strict=True)
    if any(value not in {144, 512} for value in args.segments):
        raise ValueError("this bridge diagnostic is restricted to 144/512")
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    os.environ["CZR005_CPP_PYTHON_PATH"] = str(binary.parent)

    from czr005 import cpp_backend

    module = cpp_backend.load_cpp_module(binary.parent)
    loaded_binary = Path(module.__file__).resolve(strict=True)
    if loaded_binary != binary:
        raise RuntimeError(
            f"loaded {loaded_binary}, expected explicitly requested {binary}"
        )
    native_doc = module.g4irsf11_event_runtime_from_records.__doc__ or ""
    policy_abi_available = "g4irsf17_source_policy_mode" in native_doc

    pairwise = json.loads(PAIRWISE_MODEL.read_text(encoding="utf-8"))
    published_gate = json.loads(SELECTIVE_GATE.read_text(encoding="utf-8"))
    if not isinstance(pairwise, dict) or not isinstance(published_gate, dict):
        raise TypeError("published G17 artifacts must be JSON objects")

    controls: list[dict[str, Any]] = []
    payloads: dict[int, dict[str, Any]] = {}
    for segments in args.segments:
        control, payload = _run_prefix(segments=segments, binary=binary)
        controls.append(control)
        payloads[segments] = payload

    result: dict[str, Any] = {
        "schema": "czr005.g4irsf18.g17_research_bridge_diagnostic.v1",
        "binary": str(binary),
        "published_production_authorization": {
            "authorized": published_gate.get("authorized"),
            "runtime_closed_loop_authorized": published_gate.get(
                "runtime_closed_loop_authorized"
            ),
            "unchanged": True,
        },
        "native_interface": {
            "g4irsf17_source_policy_abi_available": policy_abi_available,
            "last_supported_g17_tail": (
                "g4irsf17_source_policy_trace_limit"
                if policy_abi_available
                else "g4irsf17_source_wait_trace_limit"
            ),
        },
        "control_runs": controls,
        "shadow_runs": [],
        "research_closed_loop": {
            "requested": bool(args.research_closed_loop),
            "executed": False,
        },
    }

    if not policy_abi_available:
        result.update(
            status="BLOCKED_ABI_MISSING_SOURCE_POLICY_TAIL",
            blocker=(
                "The requested native module cannot accept the three G17 "
                "source-policy arguments. Exact 39D proposals and action "
                "mutations are therefore unobservable on this binary."
            ),
            claim_boundary=(
                "Control safety/TTH is measured. This is not 39D native "
                "parity, a learned closed loop, or production authorization."
            ),
        )
    else:
        published_bundle = (
            cpp_backend.g4irsf17_pairwise_ensemble_source_policy_artifact(
                pairwise,
                published_gate,
                supervisor_authorized=True,
            )
        )
        selector = published_gate["selector"]
        for segments in args.segments:
            shadow_result, shadow_payload = _run_prefix(
                segments=segments,
                binary=binary,
                policy_mode="shadow",
                policy_artifact=published_bundle,
            )
            shadow_result["policy"] = _policy_shadow_summary(
                shadow_payload, selector
            )
            result["shadow_runs"].append(shadow_result)

        shadows_safe = all(
            row["hard_safety"]["pass"] for row in result["shadow_runs"]
        )
        has_proposal = any(
            row["policy"]["alternative_proposal_count"] > 0
            for row in result["shadow_runs"]
        )
        if args.research_closed_loop and shadows_safe and has_proposal:
            research_gate = copy.deepcopy(published_gate)
            research_gate["authorized"] = True
            research_gate["runtime_closed_loop_authorized"] = True
            research_gate["authorization_scope"] = (
                "g4irsf18_ephemeral_research_only_not_production"
            )
            research_selector = research_gate["selector"]
            research_selector["benefit_probability_lcb_min"] = 0.5
            research_selector["harm_probability_ucb_max"] = 1.0
            research_selector["utility_lcb_min_seconds"] = -1.0e12
            research_bundle = (
                cpp_backend.g4irsf17_pairwise_ensemble_source_policy_artifact(
                    pairwise,
                    research_gate,
                    supervisor_authorized=True,
                )
            )
            research_result, research_payload = _run_prefix(
                segments=144,
                binary=binary,
                policy_mode="closed_loop",
                policy_artifact=research_bundle,
            )
            research_result["policy"] = _policy_shadow_summary(
                research_payload, research_selector
            )
            result["research_closed_loop"] = {
                "requested": True,
                "executed": True,
                "scope": "fixed_144_ephemeral_research_only",
                "published_artifacts_written": False,
                "result": research_result,
            }
        result["status"] = "NATIVE_SHADOW_COMPLETE"
        result["claim_boundary"] = (
            "Published production authorization remains false. Any optional "
            "closed loop is a fixed-144 research simulation only."
        )

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
