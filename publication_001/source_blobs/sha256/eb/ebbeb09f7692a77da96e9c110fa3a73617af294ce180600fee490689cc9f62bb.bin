"""Frozen, finite native receiving/alternative-supply causal diagnosis."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

from .assess_joint_window_protection import compare
from .joint_window_repair import submit_action
from .native_host import load_native
from .p5_handoff import FACTORS, HORIZON, build_domain, scenario_input
from .validate_joint_window_repair import evaluate

EXPECTED = "19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def summarize(rows, selected, ids):
    by_id = {r["action_id"]: r for r in rows}
    policies = {name: by_id.get(identity) for name, identity in selected.items()}
    report = {"policies": {}, "reference": {}, "global_optimality": "unknown"}
    for name, row in policies.items():
        if row is None:
            report["policies"][name] = {"status": "unknown_unexecuted"}
            continue
        clean = {k: row.get(k) for k in ("action_id", "status", "metrics", "audit", "resolutions", "physical_sha256")}
        clean["comparisons"] = {}
        if row.get("metrics"):
            for baseline in ("ordinary_arrival_assignment", "strong_service_assignment", "WAIT"):
                target = policies[baseline]
                if target and target.get("metrics"):
                    clean["comparisons"][baseline] = compare(row["metrics"], target["metrics"], ids)
        report["policies"][name] = clean
    resolved = {"verified", "asynchronous_rejected", "rejected_submission"}
    complete = len(rows) == len(by_id) and all(r.get("completion", {}).get("status") == "reached"
                                             and r["status"] in resolved for r in rows)
    for baseline in ("ordinary_arrival_assignment", "strong_service_assignment", "WAIT"):
        target = policies[baseline]
        if not target or not target.get("metrics"):
            report["reference"][baseline] = {"status": "unknown_missing_baseline"}
            continue
        feasible = [r for r in rows if r["status"] == "verified" and compare(r["metrics"], target["metrics"], ids)["preserved"]]
        best = min(feasible, key=lambda r: (r["metrics"]["cost"], r["action_id"]), default=None)
        report["reference"][baseline] = {"status": "complete_executed_finite_domain" if complete else "unknown_incomplete_domain",
            "feasible_count": len(feasible), "best_action_id": best["action_id"] if best else None,
            "best_cost": best["metrics"]["cost"] if best else None,
            "headroom_vs_baseline": target["metrics"]["cost"]-best["metrics"]["cost"] if best and complete else None,
            "scope": "this finite action domain, same fixed native continuation, all declared business identities; no global or online oracle claim"}
    return report


def pending_feedback_boundary(parent, ordinary, observation):
    """One actual source-response event, preserving every hard obligation.

    The pending source intents are cancelled through the native endpoint.
    No physics is rolled back and no receiver grant is removed. This prepares
    the same pending-prefix boundary for every finite feedback alternative.
    """
    branch = parent.fork()
    initial = submit_action(branch, ordinary, observation)
    if initial["status"] != "submitted" or not initial["submissions"]:
        raise ValueError("handoff:missing_initial_pending_bundle")
    delivery = max(r["request"]["issued_at"]+r["request"]["message_delay"] for r in initial["submissions"])
    advance = branch.advance_to(delivery, max_events=100000)
    if advance["status"] != "reached" or not advance["horizon_complete"]:
        raise ValueError("handoff:partial_response_boundary")
    observed = branch.observe("A")
    identities = {s["request"]["request_id"] for s in initial["submissions"]}
    active = [r for r in observed["transfers"] if r["request_id"] in identities]
    if len(active) != len(identities) or any(r["status"] != "pending" for r in active):
        raise ValueError("handoff:feedback_must_not_cancel_hard_or_missing_requests")
    cancelled = []
    for identity in sorted(identities):
        reply = branch.cancel_transfer_intent(identity, "A")
        cancelled.append({"request_id": identity, "reply": reply})
        if reply["status"] != "cancelled":
            raise ValueError("handoff:partial_cancel_unknown")
    return branch, {"initial": initial, "advance": advance, "before_cancel_observation": observed,
        "cancellations": cancelled, "atomic": False, "trigger": "actual source request delivery with pending soft bundle"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-seconds", type=float, default=180.)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error("--max-seconds must be finite and positive")
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).parent
    sources = [Path(__file__), *(here/name for name in ("p5_handoff.py", "joint_window_repair.py", "boundary_reference.py",
        "analytic_control.py", "native_host.py", "finite_reference.py", "validate_joint_window_repair.py",
        "validate_analytic_control.py", "assess_joint_window_protection.py"))]
    before = {str(p): sha(p) for p in sources}
    archive = args.output/"source_archive"; archive.mkdir()
    for path in sources:
        (archive/path.name).write_bytes(path.read_bytes())
    receipt = {"schema": "g31.handoff_diagnostic.v1", "status": "preparing", "source_before": before,
        "binary_sha256": sha(args.binary), "expected_binary_sha256": EXPECTED, "cases": {},
        "novelty": "research diagnostic; assignment, receiving windows and generic joint enumeration are not claimed new",
        "complete_100ms_requirement_certified": False}
    plan = {"factors": FACTORS, "horizon": HORIZON, "max_actions_per_factor": 64,
        "max_seconds": args.max_seconds, "per_branch_native_events": 100000,
        "continuation": "unchanged native S4; no later external controller decisions",
        "information": "A local business contracts and source release projections plus actual delayed C to A next-node forecast",
        "native_interface": "legacy owner-restricted live endpoints; owner_protocol not enabled",
        "protection": "all six offered jobs against ordinary, strong service assignment, and WAIT separately",
        "postrun_reference": "all finite proposals physically executed including conditional conflicts and partial matchings",
        "epochs": ["initial planning", "one real pending source-response boundary, cancel soft bundle and replan"],
        "max_total_native_branches": 256,
        "nearest_neighbors": ["https://arxiv.org/abs/2110.14891", "https://arxiv.org/abs/2603.28968"]}
    write(args.output/"plan.json", plan)
    inputs = {}
    for factor in FACTORS:
        folder = args.output/factor["name"]; folder.mkdir()
        inputs[factor["name"]] = scenario_input(factor)
        write(folder/"input.json", inputs[factor["name"]])
    receipt["predeclared_plan_sha256"] = sha(args.output/"plan.json")
    receipt["predeclared_input_sha256"] = {name: sha(args.output/name/"input.json") for name in inputs}
    write(args.output/"receipt.json", receipt)
    started = time.perf_counter()
    branch_count = 0
    try:
        if receipt["binary_sha256"] != EXPECTED:
            raise ValueError("handoff:unexpected_native_build")
        if args.prepare_only:
            receipt["status"] = "prepared_before_native_execution"
        else:
            native = load_native(args.binary)
            for factor in FACTORS:
                if time.perf_counter()-started >= args.max_seconds or branch_count >= 256:
                    break
                name = factor["name"]; data = inputs[name]; folder = args.output/name
                parent = native.NativeSession(data)
                first = parent.advance_to(.05, max_events=100000)
                if first["status"] != "reached" or not first["horizon_complete"]:
                    raise ValueError("handoff:incomplete_prefix")
                publication = parent.publish_service_forecast("C", "A", "TP", 3, .02)
                if publication["status"] != "pending":
                    raise ValueError("handoff:lawful_publication_failed")
                advance = parent.advance_to(.11, max_events=100000)
                if advance["status"] != "reached" or not advance["horizon_complete"]:
                    raise ValueError("handoff:incomplete_decision_boundary")
                observation = parent.observe("A")
                domain = build_domain(observation)
                write(folder/"prefix_publication.json", publication)
                write(folder/"observation.json", observation)
                write(folder/"domain.json", domain)
                if domain["status"] != "complete_finite_public_domain":
                    receipt["cases"][name] = {"status": domain["status"]}
                    continue
                parent_hash = parent.offline_state_sha256()
                rows = []
                with gzip.open(folder/"native_branches.jsonl.gz", "wt", encoding="utf-8") as stream:
                    for action in domain["actions"]:
                        if time.perf_counter()-started >= args.max_seconds or branch_count >= 256:
                            break
                        branch_count += 1
                        try:
                            row = evaluate(parent, data, observation, action, HORIZON)
                        except Exception:
                            row = {"action_id": action["action_id"], "status": "execution_exception", "exception": traceback.format_exc()}
                        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
                        rows.append({k: v for k, v in row.items() if k != "result"})
                assessment = summarize(rows, domain["selected"], [j["business_bag_id"] for j in data["jobs"]])
                assessment.update({"declared_actions": len(domain["actions"]), "executed_actions": len(rows),
                    "all_actions_attempted": len(rows) == len(domain["actions"]),
                    "parent_state_unchanged": parent.offline_state_sha256() == parent_hash,
                    "statuses": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
                    "compute_ms": domain["compute_ms"], "raw_sha256": sha(folder/"native_branches.jsonl.gz")})
                if not assessment["all_actions_attempted"]:
                    for ref in assessment["reference"].values():
                        ref["status"] = "unknown_incomplete_domain"; ref["headroom_vs_baseline"] = None
                    assessment["rolling"] = {"status": "unknown_budget_not_started", "all_actions_attempted": False}
                    write(folder/"assessment.json", assessment)
                    receipt["cases"][name] = assessment
                    break
                # Second, actual rolling epoch; same original physical input.
                # The initial bundle and both cancelled source responses are
                # retained in every native sibling and its raw receipts.
                ordinary = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["ordinary_arrival_assignment"])
                rolling, boundary = pending_feedback_boundary(parent, ordinary, observation)
                fresh = rolling.observe("A")
                rolling_domain = build_domain(fresh)
                rolling_folder = folder/"rolling"; rolling_folder.mkdir()
                write(rolling_folder/"boundary.json", boundary)
                write(rolling_folder/"observation.json", fresh)
                write(rolling_folder/"domain.json", rolling_domain)
                if rolling_domain["status"] != "complete_finite_public_domain":
                    assessment["rolling"] = {"status": rolling_domain["status"], "all_actions_attempted": False}
                else:
                    rolling_hash = rolling.offline_state_sha256()
                    rolling_rows = []
                    with gzip.open(rolling_folder/"native_branches.jsonl.gz", "wt", encoding="utf-8") as stream:
                        for action in rolling_domain["actions"]:
                            if time.perf_counter()-started >= args.max_seconds or branch_count >= 256:
                                break
                            branch_count += 1
                            try:
                                row = evaluate(rolling, data, fresh, action, HORIZON)
                            except Exception:
                                row = {"action_id": action["action_id"], "status": "execution_exception", "exception": traceback.format_exc()}
                            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
                            rolling_rows.append({k: v for k, v in row.items() if k != "result"})
                    feedback = summarize(rolling_rows, rolling_domain["selected"], [j["business_bag_id"] for j in data["jobs"]])
                    feedback.update({"declared_actions": len(rolling_domain["actions"]), "executed_actions": len(rolling_rows),
                        "all_actions_attempted": len(rolling_rows) == len(rolling_domain["actions"]),
                        "parent_state_unchanged": rolling.offline_state_sha256() == rolling_hash,
                        "statuses": {s: sum(r["status"] == s for r in rolling_rows) for s in sorted({r["status"] for r in rolling_rows})},
                        "raw_sha256": sha(rolling_folder/"native_branches.jsonl.gz")})
                    for p, row in feedback["policies"].items():
                        if row.get("metrics"):
                            row["compared_with_original_ordinary"] = compare(row["metrics"],
                                assessment["policies"]["ordinary_arrival_assignment"]["metrics"], [j["business_bag_id"] for j in data["jobs"]])
                    if not feedback["all_actions_attempted"]:
                        for ref in feedback["reference"].values():
                            ref["status"] = "unknown_incomplete_domain"; ref["headroom_vs_baseline"] = None
                    write(rolling_folder/"assessment.json", feedback)
                    assessment["rolling"] = feedback
                write(folder/"assessment.json", assessment)
                receipt["cases"][name] = assessment
                write(args.output/"receipt.json", receipt)
            receipt["status"] = "executed_finite_diagnostic" if all(c.get("all_actions_attempted") and c.get("parent_state_unchanged")
                and c.get("rolling", {}).get("all_actions_attempted") and c.get("rolling", {}).get("parent_state_unchanged")
                for c in receipt["cases"].values()) and len(receipt["cases"]) == len(FACTORS) else "unknown_incomplete_campaign"
    except Exception:
        receipt["status"] = "failed_campaign"; receipt["exception"] = traceback.format_exc()
        raise
    finally:
        receipt["elapsed_seconds"] = time.perf_counter()-started
        receipt["native_branches_attempted"] = branch_count
        receipt["source_after"] = {str(p): sha(p) for p in sources}
        receipt["source_changed"] = [p for p in before if before[p] != receipt["source_after"][p]]
        if receipt["source_changed"]:
            receipt["status"] = "source_changed_unfrozen_execution"
        write(args.output/"receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "source_changed": receipt["source_changed"],
        "cases": {n: {"count": c.get("executed_actions"), "statuses": c.get("statuses"),
            "costs": {p: r.get("metrics", {}).get("cost") for p, r in c.get("policies", {}).items()}}
            for n, c in receipt["cases"].items()}}))
    return 0 if receipt["status"] in ("executed_finite_diagnostic", "prepared_before_native_execution") else 1


if __name__ == "__main__":
    raise SystemExit(main())
