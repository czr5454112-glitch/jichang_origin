"""Predeclared bounded P5 branch-C experiment, exclusively native physics."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .finite_reference import _horizon_completion, outcome_cost, service_dominates
from .joint_window_repair import build_domain, digest, submit_action
from .native_host import audit_result, load_native, prepare_input
from .validate_analytic_control import replay_input, write


SCENARIOS = [
    {"name": "short_shared_receiving", "length": .4, "speed": 1., "future_source": False},
    {"name": "long_2000m", "length": 2000., "speed": 5., "future_source": False},
    {"name": "long_5000m", "length": 5000., "speed": 5., "future_source": False},
    {"name": "long_2000m_unknown_source_demand", "length": 2000., "speed": 5., "future_source": True},
]


def scenario_input(spec: dict) -> dict:
    edges = [(7, 0, .4, 1.), (8, 1, .4, 1.),
             (0, 2, spec["length"], spec["speed"]), (1, 2, spec["length"], spec["speed"]),
             (2, 3, .4, 1.), (2, 4, .6, 1.), (2, 10, .3, 1.),
             (3, 5, .8, 1.), (4, 6, .8, 1.), (5, 7, .5, 1.), (6, 8, .5, 1.), (9, 2, .8, 1.)]
    owner = lambda n: "A" if n in (0, 1, 2, 7, 8) else "B" if n in (3, 4) else "C"
    jobs = [{"business_bag_id": name, "origin": source, "destination": target,
             "arrival": arrival, "deadline": 4500., "load_seconds": load,
             "unload_seconds": .1, "hold_seconds": .1, "protected_service": True,
             "allow_suffix_reroute": True}
            for name, source, target, arrival, load in
            [("U0", 7, 0, 0., .1), ("U1", 8, 1, 0., .1),
             ("D0", 3, 5, 0., .1), ("D1", 4, 6, 0., .1), ("P", 9, 10, 0., .8)]]
    if spec["future_source"]:
        # Same public checkpoint as long_2000m. Cannot be used by selection.
        jobs.append({"business_bag_id": "UNSEEN", "origin": 0, "destination": 10,
                     "arrival": .9, "deadline": 4500., "load_seconds": .1,
                     "unload_seconds": .1, "hold_seconds": .1,
                     "protected_service": True, "allow_suffix_reroute": True})
    return prepare_input({"schema": "g31.circulation.input.v1",
        "model_scope": "synthetic predeclared branch-C 2-supply shared incoming capacity; not original map",
        "node_records": [(n, 1, .05, n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(11)],
        "edge_records": edges,
        "node_contracts": [{"node": n, "zone": owner(n), "capacity": 1} for n in range(11)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": .2}
                           for u, v, _, _ in edges],
        "trays": [{"tray_id": "T0", "node": 7}, {"tray_id": "T1", "node": 8},
                  {"tray_id": "TP", "node": 9}],
        "jobs": jobs, "transfers": [], "faults": [],
        "options": {"max_simulation_time": 5001, "max_events": 100000}})


def prefix(native, data):
    parent = native.NativeSession(data)
    parent.advance_to(.05)
    forecast = parent.publish_service_forecast("C", "A", "TP", 2, .02)
    demand = parent.publish_demand("B", "A", .02)
    if forecast["status"] == "rejected" or demand["status"] == "rejected":
        raise AssertionError((forecast, demand))
    parent.advance_to(.11)
    return parent, {"service_forecast": forecast, "demand": demand}


def evaluate(parent, data, observation, action, horizon):
    started = time.perf_counter()
    branch = parent.fork()
    submission = submit_action(branch, action, observation)
    result = branch.result_at(horizon)
    completion = _horizon_completion(result, branch, horizon)
    row = {"action_id": action["action_id"], "submission": submission, "result": result,
           "completion": completion, "status": "unknown", "conditional_conflicts": action["conditional_conflicts"]}
    if completion["status"] == "reached":
        row["audit"] = audit_result(replay_input(data, submission["submissions"]), result)
        row["metrics"] = outcome_cost(result, data["jobs"], horizon)
        submitted = {s["request"]["request_id"] for s in submission["submissions"]}
        row["resolutions"] = [r for r in result["transfers"] if r["request_id"] in submitted]
        if submission["status"] == "stale_read_set":
            row["status"] = "unresolved_read_set"
        elif any(s["reply"].get("status") in ("timeout_unknown", "failed_no_safe_continuation")
                 for s in submission["submissions"]):
            row["status"] = "unresolved_submission"
        elif submission["status"] != "submitted":
            row["status"] = "rejected_submission"
        elif any(r["status"] in ("rejected", "failed", "expired", "cancelled") for r in row["resolutions"]):
            row["status"] = "asynchronous_rejected"
        elif len(row["resolutions"]) != len(submitted) or any(r["status"] != "received" for r in row["resolutions"]):
            row["status"] = "unresolved_at_horizon"
        else:
            row["status"] = "verified"
        # Identity excludes request names; equal physical plans are deduplicated.
        row["physical_sha256"] = digest([{k: r[k] for k in
            ("time", "event", "tray_id", "business_bag_id", "node", "from", "to") if k in r}
            for r in result["receipts"] if r["event"] in ("EDGE_ENTER", "EDGE_EXIT", "LOAD_START",
                "UNLOAD_COMPLETE", "HOLD_COMPLETE", "EMPTY_RECEIVED")])
    row["elapsed_seconds"] = time.perf_counter() - started
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), Path(__file__).with_name("joint_window_repair.py"),
             Path(__file__).with_name("analytic_control.py"), Path(__file__).with_name("boundary_reference.py"),
             Path(__file__).with_name("finite_reference.py"), Path(__file__).with_name("native_host.py")]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt = {"schema": "g31.joint_window_repair.v1", "status": "running", "source_before": before,
               "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(), "cases": [],
               "novelty": "not_established", "P5_gate": "research_candidate",
               "atomic_multi_owner_commit": False, "global_native_optimality": "unknown"}
    # Preregister the finite factors, intervention grid, budget and negative
    # outcomes before executing the first branch. No adaptive winning search.
    write(args.output / "protocol.json", {"scenarios": SCENARIOS[:args.cases], "horizon": 5000,
        "max_actions_per_case": 256, "max_seconds_per_case": 120, "source_before": before,
        "public_domain": "all partial injective 2-tray assignments; point/window/window+longest-incoming-span",
        "longline_protocol_probe": "at t=2 countermand first already-entered ordinary return; native must refuse without mutation",
        "continuation": "same mature native S4, no further external control; all original jobs retained",
        "normal_service": "strict per-job non-worsening relative to ordinary_public_windows under common future",
        "role": "development falsification; no airport performance or paper novelty claim"})
    write(args.output / "receipt.json", receipt)
    public = {}
    try:
        native = load_native(args.binary)
        for spec in SCENARIOS[:args.cases]:
            folder = args.output / spec["name"]
            folder.mkdir()
            data = scenario_input(spec)
            parent, publication = prefix(native, data)
            observation = parent.observe("A")
            public[spec["name"]] = observation
            domain = build_domain(observation)
            assert domain["status"] == "complete_finite_public_domain", domain["status"]
            write(folder / "input.json", data)
            write(folder / "public_observation.json", observation)
            write(folder / "domain.json", domain)
            write(folder / "publication.json", publication)
            before_parent = parent.offline_state_sha256()
            rows, started = [], time.perf_counter()
            for action in domain["actions"]:
                if time.perf_counter() - started > 120:
                    break
                rows.append(evaluate(parent, data, observation, action, 5000))
            assert parent.offline_state_sha256() == before_parent
            ordinary = next((r for r in rows if r["action_id"] == domain["selected"]["ordinary_public_windows"]), None)
            for row in rows:
                row["paired_service_preserved"] = bool(ordinary and "metrics" in ordinary and "metrics" in row
                    and service_dominates(row["metrics"], ordinary["metrics"]))
            protected = [r for r in rows if r["status"] == "verified" and r["paired_service_preserved"]]
            exhaustive = len(rows) == len(domain["actions"]) and all(r["status"] in
                ("verified", "asynchronous_rejected", "rejected_submission") for r in rows)
            best = min(protected, key=lambda r: (r["metrics"]["cost"], r["action_id"]), default=None)
            comparisons = {}
            for name, action_id in domain["selected"].items():
                found = next((r for r in rows if r["action_id"] == action_id), None)
                comparisons[name] = {k: found[k] for k in ("action_id", "status", "metrics", "paired_service_preserved")
                                     if found and k in found}
            # Actual stale owner state check is mutation-free on rejection.
            stale = parent.fork()
            stale.advance_to(.8)
            stale_before = stale.offline_state_sha256()
            stale_reply = submit_action(stale, domain["actions"][-1], observation)
            assert stale_reply["status"] == "stale_read_set" and stale.offline_state_sha256() == stale_before
            inflight_probe = None
            if spec["length"] >= 2000 and not spec["future_source"]:
                action = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["ordinary_public_windows"])
                inflight = parent.fork()
                submitted = submit_action(inflight, action, observation)
                inflight.advance_to(2.)
                first_id = submitted["submissions"][0]["request"]["request_id"]
                visible = inflight.observe("A")
                before_cancel = inflight.offline_state_sha256()
                cancel = inflight.cancel_transfer_intent(first_id, "A")
                assert cancel["status"] == "rejected" and cancel["reason"] == "already_committed", cancel
                assert inflight.offline_state_sha256() == before_cancel
                actual_tray = next(t for t in visible["trays"] if t["tray_id"] == "T0")
                assert actual_tray["edge_from"] == 0 and actual_tray["edge_to"] == 2, actual_tray
                after = inflight.result_at(5000)
                assert _horizon_completion(after, inflight, 5000)["status"] == "reached"
                for key in ("jobs", "trays", "receipts", "transfers"):
                    assert after[key] == ordinary["result"][key], key
                inflight_probe = {"request_id": first_id, "observed_tray": actual_tray,
                                  "cancel_reply": cancel, "physics_matches_uncancelled": True}
                write(folder / "inflight_no_recall.json", inflight_probe)
            with gzip.open(folder / "native_branches.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(rows, handle, ensure_ascii=False, allow_nan=False)
            summary = {"scenario": spec, "domain_size": len(domain["actions"]), "evaluated": len(rows),
                "exhaustive": exhaustive, "finite_optimality": "optimal_in_enumerated_domain" if exhaustive and best else "unknown",
                "global_optimality": "unknown", "protected_candidates": len(protected),
                "distinct_physical_outcomes": len({r["physical_sha256"] for r in rows if "physical_sha256" in r}),
                "conditional_joint_conflicts": sum(bool(a["conditional_conflicts"]) for a in domain["actions"]),
                "statuses": {s: sum(r["status"] == s for r in rows) for s in {r["status"] for r in rows}},
                "policies": comparisons, "best_action_id": best["action_id"] if best else None,
                "baseline_execution_status": ordinary["status"] if ordinary else "unknown",
                "headroom_scope": "same_finite_domain_against_complete_baseline" if ordinary and
                    ordinary["status"] == "verified" else "offline_common_future_outcome_gap_against_failed_requested_baseline",
                "reference_headroom": ordinary["metrics"]["cost"] - best["metrics"]["cost"] if ordinary and best else None,
                "stale_read_set_actual_reply": stale_reply, "public_compute_ms": domain["compute_ms"],
                "longline_inflight_countermand": inflight_probe,
                "native_reference_seconds": time.perf_counter() - started}
            write(folder / "summary.json", summary)
            receipt["cases"].append(summary)
            write(args.output / "receipt.json", receipt)
        if "long_2000m_unknown_source_demand" in public:
            receipt["unknown_future_identical_public_projection"] = (
                public["long_2000m"] == public["long_2000m_unknown_source_demand"])
            assert receipt["unknown_future_identical_public_projection"]
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        receipt["source_changed"] = [p for p in paths if before[str(p)] != receipt["source_after"][str(p)]]
        receipt["source_changed"] = list(map(str, receipt["source_changed"]))
        write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "cases": [{"name": c["scenario"]["name"],
        "reference_headroom": c["reference_headroom"], "domain": c["domain_size"],
        "statuses": c["statuses"]} for c in receipt["cases"]]}))


if __name__ == "__main__":
    main()
