"""Paired native continuation after an actually observed source-demand change."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .finite_reference import _horizon_completion, outcome_cost, service_dominates
from .joint_window_feedback import repair_observed_source_change
from .joint_window_repair import build_domain, submit_action
from .native_host import audit_result, load_native
from .validate_analytic_control import replay_input, write
from .validate_joint_window_repair import SCENARIOS, prefix, scenario_input


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), Path(__file__).with_name("joint_window_feedback.py"),
             Path(__file__).with_name("joint_window_repair.py"), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("finite_reference.py")]
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(args.output / "protocol.json", {"scenarios": [SCENARIOS[1], SCENARIOS[3]],
        "boundary": .91, "schedule": ".11 + eight .1 control ticks for both worlds; not triggered by hidden future tape",
        "intervention": "cancel own uncommitted stale-source promises, preserve remaining assignment, retime after observed change",
        "comparators": ["frozen_joint", "one_round_observed_source_feedback", "ordinary_public_windows"],
        "horizon": 5000, "budget": "six full native continuations, no sweep", "novelty": "not_established"})
    native = load_native(args.binary)
    receipt = {"schema": "g31.observed_source_feedback.v1", "status": "running", "cases": [],
               "source_before": sources, "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest()}
    for scenario in [SCENARIOS[1], SCENARIOS[3]]:
        data = scenario_input(scenario)
        parent, publication = prefix(native, data)
        observation = parent.observe("A")
        domain = build_domain(observation)
        rows = []
        for policy in ("frozen_joint", "one_round_observed_source_feedback", "ordinary_public_windows"):
            branch = parent.fork()
            key = "ordinary_public_windows" if policy == "ordinary_public_windows" else "joint_conditional_repair"
            action = next(a for a in domain["actions"] if a["action_id"] == domain["selected"][key])
            first = submit_action(branch, action, observation)
            branch.advance_to(.91)
            repair = repair_observed_source_change(branch, "A", [s["request"]["request_id"] for s in first["submissions"]]) \
                     if policy == "one_round_observed_source_feedback" else {"status": "not_requested", "submissions": []}
            result = branch.result_at(5000)
            completion = _horizon_completion(result, branch, 5000)
            if completion["status"] != "reached":
                raise AssertionError(completion)
            submissions = first["submissions"] + repair["submissions"]
            audit = audit_result(replay_input(data, submissions), result)
            metrics = outcome_cost(result, data["jobs"], 5000)
            rows.append({"policy": policy, "repair": repair, "initial_submission": first,
                         "result": result, "metrics": metrics, "audit": audit, "completion": completion})
        ordinary = rows[2]["metrics"]
        for row in rows:
            row["paired_vs_ordinary_all_offered"] = service_dominates(row["metrics"], ordinary)
        folder = args.output / scenario["name"]
        folder.mkdir()
        write(folder / "input.json", data)
        with gzip.open(folder / "native_continuations.json.gz", "wt", encoding="utf-8") as handle:
            json.dump(rows, handle, allow_nan=False)
        receipt["cases"].append({"scenario": scenario, "policies": [{"policy": r["policy"],
            "cost": r["metrics"]["cost"], "metrics": r["metrics"], "repair_status": r["repair"]["status"],
            "cancellations": r["repair"].get("cancellations", []),
            "paired_vs_ordinary_all_offered": r["paired_vs_ordinary_all_offered"]} for r in rows]})
    receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt["source_changed"] = [p for p in sources if sources[p] != receipt["source_after"][p]]
    receipt["status"] = "passed"
    receipt["novelty"] = "not_established; conventional_one_round_feedback_strong_comparator"
    write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "cases": [{"name": c["scenario"]["name"],
        "policies": [{k: p[k] for k in ("policy", "cost", "repair_status", "paired_vs_ordinary_all_offered")}
                     for p in c["policies"]]} for c in receipt["cases"]]}))


if __name__ == "__main__":
    main()
