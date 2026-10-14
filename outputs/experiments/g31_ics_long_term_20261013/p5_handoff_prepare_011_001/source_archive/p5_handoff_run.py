"""Frozen, finite native receiving/alternative-supply causal diagnosis."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .assess_joint_window_protection import compare
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
    complete = len(rows) == len(by_id) and all(r.get("completion", {}).get("status") == "reached" for r in rows)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-seconds", type=float, default=180.)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
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
    try:
        if receipt["binary_sha256"] != EXPECTED:
            raise ValueError("handoff:unexpected_native_build")
        if args.prepare_only:
            receipt["status"] = "prepared_before_native_execution"
        else:
            native = load_native(args.binary)
            for factor in FACTORS:
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
                        if time.perf_counter()-started >= args.max_seconds:
                            break
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
                write(folder/"assessment.json", assessment)
                receipt["cases"][name] = assessment
                write(args.output/"receipt.json", receipt)
            receipt["status"] = "executed_finite_diagnostic" if all(c.get("all_actions_attempted") and c.get("parent_state_unchanged")
                for c in receipt["cases"].values()) and len(receipt["cases"]) == len(FACTORS) else "unknown_incomplete_campaign"
    except Exception:
        receipt["status"] = "failed_campaign"; receipt["exception"] = traceback.format_exc()
        raise
    finally:
        receipt["elapsed_seconds"] = time.perf_counter()-started
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
