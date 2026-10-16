"""Fixed exogenous protocol-outage domain: unchanged four jobs and capacities.

The future outage schedule is never passed to the initial owner proposal.
Nine healthy rows are reused verbatim; 108 new native branches cover paired
feedback controls and all31 offline fixed-route departure candidates per gate.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from . import research_native_public_joint as online
from . import research_synthetic_reuse_chain as v1
from . import research_synthetic_reuse_v2 as v2
from .native_host import load_native


def outage_contract():
    data = v1.scene(0.)
    service1 = next(n[2] for n in data["node_records"] if n[0] == 1)
    return {"owner": "B", "start": v1.START + .5 * .01, "end": 2 * v1.PUBLIC_RECEIVER_LOAD + service1}


def reference_times():
    data = v1.scene(0.)
    first = next(j for j in data["jobs"] if j["business_bag_id"] == "loaded")
    duration_input = {"contract": data, "jobs": {"loaded": {"loaded_at": first["arrival"] + first["load_seconds"]}}}
    actions, _ = online.model.candidates_from_durations(duration_input)
    return [a["departure"] for a in actions if a["initial_next"] == 1]


def protocol():
    rows = {}
    for regime in ("healthy", "outage"):
        for gate in v1.GATES:
            for policy in ("incumbent", "fixed_route_model", "joint_model", "joint_no_feedback"):
                rows[f"{regime}/gate{int(gate)}/{policy}"] = {"regime": regime, "gate": gate, "policy": policy,
                    "scope": "online_initial_proposal_common_continuation", "status": "unknown_unexecuted",
                    "reuse_prior": regime == "healthy" and policy != "joint_no_feedback"}
    for gate in v1.GATES:
        for index, departure in enumerate(reference_times()):
            rows[f"outage/gate{int(gate)}/offline_time{index:02d}"] = {"regime": "outage", "gate": gate,
                "policy": "offline_fixed_reference", "departure": departure, "scope": "offline_finite_reference_only",
                "status": "unknown_unexecuted", "reuse_prior": False}
    return {"schema": "g31.lt2.public_joint_feedback_outage.v1", "maximum_new_native_branches": 108,
        "row_denominator": 117, "reused_healthy_rows": 9, "rows": rows, "owner_outage": outage_contract(),
        "outage_derivation": "start=decision.11+message_delay.01/2; end=2*public receiver load3+node1service.1; fixed before outcomes",
        "input_invariants": "identical four jobs, two trays, graph, capacities, FIFO, Storage and delays; only exogenous owner-protocol outage factor differs",
        "information": "initial owner-only delivered snapshots captured.06 and selfACKed.09; decision.11 precedes fault onset.115; future schedule never passed to choose",
        "common_continuation": "v2.1 actual same-L returns, receiving_full recovery, native actualroute/ACK; paired joint_no_feedback uses explicit native_keep only later",
        "protection": "all four physical completion deltas <=0 versus same-gate same-outage incumbent and separately fixed-route model; incomplete unknown",
        "paired_causal_contrast": "joint adaptive vs joint native_keep with identical independently selected initial actions; nofeedback may fail protection",
        "stress_cost": "healthy counterpart difference reported separately, never the outage-domain protection baseline",
        "offline_reference": {"declared_fixed_domain": "same31 public-duration candidates", "departure_times": reference_times(),
            "timing_inputs": "public graph/service durations and source-known first load completion .1=arrival0+load.1; no outcome labels",
            "execution": "all31 fixed-route timings natively run in every outage gate; no collapse or omitted branch equivalence used",
            "limits": "finite predeclared31 domain only, not continuousoptimum; reference is explicitlyoffline, not policyinput"},
        "failure_handling": "retain unexecuted/incomplete/missingACK/actions/schema/source drift; no positive-outcome filtering",
        "claim_limits": ["new exogenous fault domain, not changed normal-domain result", "not full rolling MPC", "not atomic agreement", "not a novel solver", "not100ms certified"]}


def run_cell(native, row):
    data = v1.scene(row["gate"])
    if row["regime"] == "outage": data["owner_protocol"]["owner_outages"] = [outage_contract()]
    session = native.NativeSession(data)
    session.advance_to(.05)
    client = v1.Transport(session)
    channels = {o: client.submit(o, "demand", "seed-demand", target_owner=p, message_delay=.01, publication_delay=.01)
                for o, p in (("A", "B"), ("B", "A"))}
    planning = {o: client.submit(o, "planning_snapshot", "initial-planning", target_owner=p,
        message_delay=.01, publication_delay=.01, expiry=.21) for o, p in (("A", "B"), ("B", "A"))}
    session.advance_to(v1.START)
    client.refresh(retry=False)
    offline = row["policy"] == "offline_fixed_reference"
    if offline:
        selected = {"initial_next": 1, "departure": row["departure"], "later_mode": "adaptive"}
        owners = {o: {"information": online.adapter.collect_native(native, session, o, planning[o]),
            "decision": {"status": "OFFLINE_prespecified_reference_not_online_proposal", "selected_action": selected}}
            for o in ("A", "B")}
        supply = client.submit("B", "transfer", "initial-supply", tray_id="E", source=5, destination=1,
            earliest_departure=selected["departure"], expiry=39., message_delay=.01)
    else:
        policy = "joint_model" if row["policy"] == "joint_no_feedback" else row["policy"]
        # Only owner/public captured input reaches owner_first_action.
        owners = {o: online.owner_first_action(native, session, client, o, planning[o], policy) for o in ("A", "B")}
        selected = owners["A"]["decision"].get("selected_action")
        supply = owners["B"]["native_request_id"]
        if not selected or selected != owners["B"]["decision"].get("selected_action") or supply is None:
            return {"specification": row, "input": data, "owners": owners,
                    "summary": {"status": "unknown_initial_action_disagreement"}}
    selected = copy.deepcopy(selected)
    selected["later_mode"] = "native_keep" if row["policy"] == "joint_no_feedback" else "adaptive"
    continuation = v2.continue_v2(session, client, channels, supply, selected["later_mode"])
    result = session.result_at(v1.HORIZON)
    summary = v2.assess_cell(data, result, client, continuation, selected)
    return {"specification": copy.deepcopy(row), "executed_action": selected, "input": data, "owners": owners,
        "calls": client.calls, "outbox": client.rows, "continuation": continuation, "result": result, "summary": summary}


def comparison(rows):
    report = {}
    for regime in ("healthy", "outage"):
        for gate in v1.GATES:
            prefix = f"{regime}/gate{int(gate)}/"
            names = ("incumbent", "fixed_route_model", "joint_model", "joint_no_feedback")
            group = {n: rows[prefix + n] for n in names}
            if any(r["status"] != "assessed" for r in group.values()):
                report[prefix] = {"status": "unknown_incomplete_four_arm_comparison"}; continue
            completion = {n: r["summary"]["completion"] for n, r in group.items()}
            base, fixed, joint, nofeedback = [completion[n] for n in names]
            protected = lambda a, b: len(a) == len(b) == 4 and set(a) == set(b) and all(a[j] <= b[j] for j in b)
            result = {"status": "assessed", "completion": completion,
                "joint_protected_vs_incumbent": protected(joint, base), "joint_protected_vs_fixed_model": protected(joint, fixed),
                "joint_gain_vs_fixed_model": sum(fixed.values()) - sum(joint.values()),
                "feedback_gain_vs_paired_native_keep": sum(nofeedback.values()) - sum(joint.values()),
                "feedback_per_job_delta": {j: joint[j] - nofeedback[j] for j in joint},
                "feedback_protected_vs_paired_native_keep": protected(joint, nofeedback),
                "native_keep_protected_vs_incumbent": protected(nofeedback, base)}
            if regime == "outage":
                refs = [rows[prefix + f"offline_time{i:02d}"] for i in range(31)]
                result["offline_reference_status"] = "assessed_all31_native_candidates" if all(r["status"] == "assessed" for r in refs) else "unknown"
                if all(r["status"] == "assessed" for r in refs):
                    eligible = [r["summary"]["completion"] for r in refs if protected(r["summary"]["completion"], base)]
                    result["offline_fixed_best_protected_completion"] = min(eligible, key=lambda x: sum(x.values())) if eligible else None
                    result["joint_gain_vs_offline_fixed31"] = min(sum(x.values()) for x in eligible) - sum(joint.values()) if eligible else None
                healthy = rows[f"healthy/gate{int(gate)}/joint_model"]
                result["joint_stress_cost_vs_healthy_per_job"] = ({j: joint[j] - healthy["summary"]["completion"][j] for j in joint}
                    if healthy["status"] == "assessed" else None)
            report[prefix] = result
    return report


def prepare(output, previous):
    output.mkdir(parents=True, exist_ok=False)
    p = protocol()
    p["previous_healthy_evidence"] = str(previous.resolve())
    sources = [Path(__file__)] + [Path(m.__file__) for m in (online, online.adapter, online.model, v1, v2)]
    p["source_sha256"] = {str(s.resolve()): online.sha(s) for s in sources}
    archive = output / "source_archive"; archive.mkdir()
    for s in sources: (archive / s.name).write_bytes(s.read_bytes())
    for key, row in p["rows"].items():
        if row["reuse_prior"]:
            src = previous / f"gate{int(row['gate'])}/{row['policy']}.json.gz"
            row["prior_file"], row["prior_sha256"] = str(src.resolve()), online.sha(src)
    online.write(output / "preregistered_protocol.json", p)
    online.write(output / "branch_ledger.json", p["rows"])
    return p


def worker(args):
    p = json.loads((args.output / "preregistered_protocol.json").read_text())
    if any(online.sha(Path(f)) != h for f, h in p["source_sha256"].items()): raise ValueError("outage:source_drift")
    if online.sha(args.binary) != args.expected_binary_sha256: raise ValueError("outage:binary_identity")
    previous_receipt = json.loads((Path(p["previous_healthy_evidence"]) / "receipt.json").read_text())
    if previous_receipt["native_binary_sha256"] != args.expected_binary_sha256: raise ValueError("outage:reused_binary_mismatch")
    native = load_native(args.binary)
    rows = copy.deepcopy(p["rows"]); native_count = 0; started = time.perf_counter()
    for key, row in rows.items():
        row["status"] = "unknown_in_progress"; online.write(args.output / "branch_ledger.json", rows)
        try:
            if row["reuse_prior"]:
                source = Path(row["prior_file"])
                if online.sha(source) != row["prior_sha256"]: raise ValueError("outage:reused_raw_drift")
                raw = json.load(gzip.open(source, "rt"))
                if raw["input"] != json.loads(json.dumps(v1.scene(row["gate"]))): raise ValueError("outage:reused_input_mismatch")
                row.update(status=raw["summary"]["status"], summary=raw["summary"], reused_verbatim=True)
            else:
                native_count += 1
                raw = run_cell(native, row)
                target = args.output / (key + ".json.gz"); target.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(target, "wt", encoding="utf-8") as stream: json.dump(raw, stream, allow_nan=False)
                row.update(status=raw["summary"]["status"], summary=raw["summary"])
        except Exception:
            row.update(status="unknown_failed", exception=traceback.format_exc())
        online.write(args.output / "branch_ledger.json", rows)
    changed = [f for f, h in p["source_sha256"].items() if online.sha(Path(f)) != h]
    receipt = {"schema": p["schema"], "status": "executed" if not changed and all(r["status"] == "assessed" for r in rows.values()) else "completed_with_unknowns",
        "denominator": len(rows), "new_native_branches": native_count, "reused_healthy_rows": sum(r.get("reused_verbatim", False) for r in rows.values()),
        "comparisons": comparison(rows), "source_changed": changed, "native_binary_sha256": args.expected_binary_sha256,
        "wall_seconds": time.perf_counter() - started, "future_fault_schedule_used_for_initial_policy": False,
        "native_forks_used": 0, "rolling_joint_optimizer_implemented": False, "atomic_agreement_implemented": False,
        "complete_request_100ms_certified": False}
    online.write(args.output / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--binary", type=Path)
    p.add_argument("--expected-binary-sha256")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--worker", action="store_true")
    p.add_argument("--timeout-seconds", type=float, default=90.)
    a = p.parse_args()
    if a.worker: worker(a); return
    prepare(a.output, a.previous)
    if not a.execute: print("prepared:108new_native_branches+9immutable_healthy_rows"); return
    if not a.binary or not a.expected_binary_sha256: p.error("binary identity required")
    command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(a.output), "--previous", str(a.previous),
        "--binary", str(a.binary), "--expected-binary-sha256", a.expected_binary_sha256]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=a.timeout_seconds)
        (a.output / "worker.stdout.log").write_text(done.stdout, encoding="utf-8")
        (a.output / "worker.stderr.log").write_text(done.stderr, encoding="utf-8")
        if done.returncode: online.write(a.output / "worker_failure.json", {"status": "unknown_worker_failed", "returncode": done.returncode})
    except subprocess.TimeoutExpired:
        online.write(a.output / "worker_failure.json", {"status": "unknown_hard_timeout", "timeout_seconds": a.timeout_seconds})


if __name__ == "__main__": main()
