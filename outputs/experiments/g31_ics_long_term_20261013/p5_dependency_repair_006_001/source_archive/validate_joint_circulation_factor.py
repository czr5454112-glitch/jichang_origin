"""Independent predeclared legal-return graph factor with common live control.

The former absorbing-terminal experiment is immutable. This new synthetic
physical contract is shared by every action/method and is not an airport fix.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .analytic_control import run_online_matching
from .assess_joint_window_protection import compare
from .finite_reference import _horizon_completion, outcome_cost, service_dominates
from .joint_window_repair import build_domain, submit_action
from .native_host import audit_result, load_native, prepare_input
from .validate_analytic_control import replay_input, write
from .validate_joint_window_repair import SCENARIOS, scenario_input


HORIZON = 2000.
CONTROL_PERIOD = 10.
OWNERS = ["A", "B", "C"]


def circulation_factor_input(spec):
    data = copy.deepcopy(scenario_input(spec))
    data["edge_records"].append((10, 7, .5, 1.))
    data["edge_contracts"].append({"from": 10, "to": 7, "capacity": 1, "entry_headway": .2})
    data["node_records"] = [tuple(list(n[:5]) + [[7]]) if n[0] == 10 else n for n in data["node_records"]]
    data["model_scope"] = "independent synthetic legal-return factor: common 10->7 edge; not original airport or retroactive repair of absorbing-terminal experiment"
    return prepare_input(data)


def common_prefix(native, data):
    session = native.NativeSession(data)
    session.advance_to(.05)
    forecast = session.publish_service_forecast("C", "A", "TP", 2, .02)
    publications, published = [], {}
    for owner in OWNERS:
        local = session.observe(owner)
        signature = sorted([j["business_bag_id"], j["origin"], j["arrival"], j.get("deadline", -1)]
                           for j in local["jobs"] if j["status"] in ("waiting", "waiting_for_tray"))
        for recipient in OWNERS:
            if recipient != owner:
                publications.append({"source": owner, "target": recipient,
                                     "reply": session.publish_demand(owner, recipient, .02)})
        published[owner] = signature
    session.advance_to(.11)
    # All channels were published once at .05. The first continuation decision
    # is 10.11; no duplicate initial publication or extra .11 R2 action is added.
    state = {"schema": "g31.analytic_controller_state.v1", "start": .11, "next_tick": 1,
             "published": published, "config": {"owners": OWNERS, "predictive": True,
                "control_period": CONTROL_PERIOD, "message_delay": .1, "demand_delay": .02,
                "publish": True, "respect_service_forecasts": True}}
    return session, state, {"forecast": forecast, "demand_publications": publications}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-seconds-per-case", type=float, default=180)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), *(Path(__file__).with_name(name) for name in (
        "joint_window_repair.py", "analytic_control.py", "assess_joint_window_protection.py",
        "finite_reference.py", "boundary_reference.py", "native_host.py",
        "validate_joint_window_repair.py", "validate_analytic_control.py"))]
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    protocol = {"schema": "g31.joint_circulation_factor_protocol.v1",
        "scenarios": [SCENARIOS[1], SCENARIOS[3]], "new_shared_edge": {"from": 10, "to": 7,
            "length": .5, "speed": 1., "capacity": 1, "entry_headway": .2},
        "initial_domain": "same 31 public initial actions; all conditional conflicts still run natively",
        "continuation": {"controller": "strong analytic predictive public windows", "owners": OWNERS,
            "phase": .11, "first_post_intervention_tick": 10.11, "period": CONTROL_PERIOD,
            "command_delay": .1, "demand_delay": .02, "compact_projection": False},
        "horizon": HORIZON, "max_seconds_per_case": args.max_seconds_per_case, "max_events": 100000,
        "protection": "all offered vs ordinary and WAIT, plus prefix P/U0/U1 vs WAIT",
        "comparison_scope": "within this new shared synthetic graph/H only; no subtraction from old absorbing graph",
        "novelty": "not_established; no training; all negative outcomes retained"}
    write(args.output / "protocol.json", protocol)
    receipt = {"schema": "g31.joint_circulation_factor.v1", "status": "running", "cases": [],
               "source_before": sources, "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),
               "protocol_sha256": hashlib.sha256((args.output / "protocol.json").read_bytes()).hexdigest()}
    write(args.output / "receipt.json", receipt)
    native = load_native(args.binary)
    public_worlds = []
    try:
        for spec in protocol["scenarios"]:
            folder = args.output / spec["name"]
            folder.mkdir()
            data = circulation_factor_input(spec)
            parent, state, publications = common_prefix(native, data)
            observed = parent.observe("A")
            public_worlds.append(observed)
            domain = build_domain(observed)
            assert domain["status"] == "complete_finite_public_domain" and len(domain["actions"]) == 31
            write(folder / "input.json", data)
            write(folder / "public_domain.json", {"observation": observed, "domain": domain})
            write(folder / "controller_prefix.json", {"controller_state": state, "publications": publications})
            parent_before = parent.offline_state_sha256()
            # Always evaluate the comparison policies first under a wall budget.
            selected = set(domain["selected"].values()) | {"WAIT"}
            actions = sorted(domain["actions"], key=lambda a: (a["action_id"] not in selected, a["action_id"]))
            rows, started = [], time.perf_counter()
            for index, action in enumerate(actions):
                if time.perf_counter() - started >= args.max_seconds_per_case:
                    break
                branch = parent.fork()
                initial = submit_action(branch, action, observed)
                follow = run_online_matching(branch, OWNERS, horizon=HORIZON, predictive=True,
                    control_period=CONTROL_PERIOD, message_delay=.1, demand_delay=.02,
                    respect_service_forecasts=True, controller_state=copy.deepcopy(state), compact_projection=False)
                result = follow["result"]
                completion = _horizon_completion(result, branch, HORIZON,
                    follow["status"] if isinstance(follow.get("status"), str) else "invalid_outer_status")
                row = {"action_id": action["action_id"], "status": "unknown", "completion": completion,
                       "initial_submission": initial, "initial_conditional_conflicts": action["conditional_conflicts"]}
                if completion["status"] == "reached":
                    replay = replay_input(data, initial["submissions"] + follow["submitted"])
                    row["audit"] = audit_result(replay, result)
                    row["metrics"] = outcome_cost(result, data["jobs"], HORIZON)
                    ids = {s["request"]["request_id"] for s in initial["submissions"]}
                    resolutions = [t for t in result["transfers"] if t["request_id"] in ids]
                    row["initial_resolutions"] = resolutions
                    if initial["status"] != "submitted":
                        row["status"] = "unresolved_submission"
                    elif any(t["status"] in ("rejected", "failed", "expired", "cancelled") for t in resolutions):
                        row["status"] = "asynchronous_rejected"
                    elif len(resolutions) != len(ids) or any(t["status"] != "received" for t in resolutions):
                        row["status"] = "unresolved_at_horizon"
                    else:
                        row["status"] = "verified"
                    row["TP_business_sequence"] = [r["business_bag_id"] for r in result["receipts"]
                        if r["tray_id"] == "TP" and r["event"] == "LOAD_START"]
                    row["TP_cross_zone_return"] = [r for r in result["receipts"]
                        if r["tray_id"] == "TP" and r["event"] in ("EXPORT_GRANTED", "EMPTY_RECEIVED")]
                raw = {"initial": initial, "controller_run": follow, "assessment": row}
                raw_name = f"branch_{index:03d}.json.gz"
                with gzip.open(folder / raw_name, "wt", encoding="utf-8") as handle:
                    json.dump(raw, handle, allow_nan=False)
                row["raw_file"] = raw_name
                row["raw_sha256"] = hashlib.sha256((folder / raw_name).read_bytes()).hexdigest()
                rows.append(row)
            assert parent.offline_state_sha256() == parent_before
            by_id = {r["action_id"]: r for r in rows}
            ordinary = by_id[domain["selected"]["ordinary_public_windows"]]
            wait = by_id["WAIT"]
            all_ids = sorted(j["business_bag_id"] for j in data["jobs"] if j["arrival"] <= HORIZON)
            for row in rows:
                if not all("metrics" in r for r in (row, ordinary, wait)):
                    continue
                row["relative_to_ordinary_all_offered"] = compare(row["metrics"], ordinary["metrics"], all_ids)
                row["relative_to_wait_all_offered"] = compare(row["metrics"], wait["metrics"], all_ids)
                row["relative_to_wait_precommitted"] = compare(row["metrics"], wait["metrics"], ["P", "U0", "U1"])
            eligible = [r for r in rows if r["status"] == "verified"
                        and r.get("relative_to_ordinary_all_offered", {}).get("preserved")]
            exhaustive = len(rows) == len(actions) and all(r["status"] in ("verified", "asynchronous_rejected") for r in rows)
            best = min(eligible, key=lambda r: r["metrics"]["cost"], default=None)
            case = {"scenario": spec, "evaluated": len(rows), "domain_size": 31, "exhaustive": exhaustive,
                    "strict_bundle_optimality": "optimal_in_this_domain_and_continuation" if exhaustive and best else "unknown",
                    "global_native_optimality": "unknown", "finite_reference_headroom":
                    ordinary["metrics"]["cost"] - best["metrics"]["cost"] if best else None,
                    "qualified_bundle_count": len(eligible), "best_action_id": best["action_id"] if best else None,
                    "initial_bundle_statuses": {s: sum(r["status"] == s for r in rows) for s in {r["status"] for r in rows}},
                    "elapsed_seconds": time.perf_counter() - started, "rows": rows,
                    "policies": {"WAIT": wait, **{name: by_id[key] for name, key in domain["selected"].items()}}}
            write(folder / "summary.json", case)
            receipt["cases"].append({k: v for k, v in case.items() if k != "rows"})
            write(args.output / "receipt.json", receipt)
        assert public_worlds[0] == public_worlds[1], "unseen_future_changed_initial_public_projection"
        receipt["initial_public_worlds_identical"] = True
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        receipt["source_changed"] = [p for p in sources if sources[p] != receipt["source_after"][p]]
        write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "cases": [{"name": c["scenario"]["name"],
        "evaluated": c["evaluated"], "headroom": c["finite_reference_headroom"],
        "policies": {name: {"cost": p.get("metrics", {}).get("cost"),
                              "completed": p.get("metrics", {}).get("completed"),
                              "TP_bags": p.get("TP_business_sequence")} for name, p in c["policies"].items()}}
        for c in receipt["cases"]]}))


if __name__ == "__main__":
    main()
