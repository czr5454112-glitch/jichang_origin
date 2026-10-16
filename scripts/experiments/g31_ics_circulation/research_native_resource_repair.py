"""Prepared fair native execution comparison of three pure repair methods."""
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
from . import public_resource_repair as repair
from . import research_native_public_joint as shared
from . import research_synthetic_reuse_chain as v1
from . import research_synthetic_reuse_v2 as v2
from .native_host import load_native


def owner_action(native, session, client, owner, own_snapshot_id, method):
    started = time.perf_counter()
    info = shared.adapter.collect_native(native, session, owner, own_snapshot_id)
    collected = time.perf_counter()
    if info["status"] != "conditional_native_delivered_model_input" or not info["native_delivery_verified"]:
        return {"owner": owner, "information": info, "proposal": {"status": "unknown_input", "selected_action": None}, "request_id": None}
    actions, incumbent = repair.model.candidates_from_durations(info["bundle"])
    proposal = repair.repair(info["bundle"], actions, incumbent, method=method, evaluation_budget=35)
    predicted = time.perf_counter()
    action = proposal["selected_action"]
    view = session.observe_protocol(owner)
    identity = None
    if action and owner == "A":
        tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["mode"] == "loaded"
                     and t["node"] == 0 and t["edge_to"] < 0 and t["business_bag_id"] == "loaded"), None)
        if tray is None: proposal = {"status": "unknown_local_tray_changed", "selected_action": None}
        elif action["initial_next"] == 2: identity = v1.request_route(client, "A", tray, 2, "initial-route")
    elif action:
        tray = next((t for t in view["trays"] if t["tray_id"] == "E" and t["mode"] == "empty"
                     and t["node"] == 5 and t["edge_to"] < 0 and t["available_at"] <= view["now"]), None)
        if tray is None: proposal = {"status": "unknown_local_tray_changed", "selected_action": None}
        else: identity = client.submit("B", "transfer", "initial-supply", tray_id="E", source=5, destination=1,
            earliest_departure=action["departure"], expiry=39., message_delay=.01)
    return {"owner": owner, "at": view["now"], "information": info, "proposal": proposal, "request_id": identity,
        "local_action_view": view, "capture_wall_ms": (collected - started) * 1000,
        "model_search_wall_ms": (predicted - collected) * 1000, "owner_call_wall_ms": (time.perf_counter() - started) * 1000}


def run(native, gate, method):
    data = v1.scene(gate)
    session = native.NativeSession(data)
    session.advance_to(.05)
    client = v1.Transport(session)
    channels = {o: client.submit(o, "demand", "seed-demand", target_owner=p, message_delay=.01, publication_delay=.01)
                for o, p in (("A", "B"), ("B", "A"))}
    planning = {o: client.submit(o, "planning_snapshot", "initial-planning", target_owner=p, message_delay=.01,
                publication_delay=.01, expiry=.21) for o, p in (("A", "B"), ("B", "A"))}
    session.advance_to(.11); client.refresh(retry=False)
    owners = {o: owner_action(native, session, client, o, planning[o], method) for o in ("A", "B")}
    selected = owners["A"]["proposal"].get("selected_action")
    if not selected or selected != owners["B"]["proposal"].get("selected_action") or not owners["B"]["request_id"]:
        return {"input": data, "owners": owners, "summary": {"status": "unknown_first_action_unready_or_disagrees"}}
    continuation = v2.continue_v2(session, client, channels, owners["B"]["request_id"], "adaptive")
    result = session.result_at(40.)
    summary = v2.assess_cell(data, result, client, continuation, selected)
    return {"input": data, "owners": owners, "calls": client.calls, "outbox": client.rows,
            "continuation": continuation, "result": result, "summary": summary}


def prepare(output, previous):
    output.mkdir(parents=True, exist_ok=False)
    rows = {f"gate{int(g)}/{m}": {"gate": g, "method": m, "status": "unknown_unexecuted"}
            for g in v1.GATES for m in repair.METHODS}
    sources = [Path(__file__)] + [Path(m.__file__) for m in (repair, repair.model, shared, shared.adapter, v1, v2)]
    p = {"schema": "g31.lt2.native_resource_repair_comparison.v1", "native_branch_budget": 9,
        "methods": list(repair.METHODS), "budget_per_owner": 35, "rows": rows,
        "initial_information": "each owner only native-delivered peer snapshot+own delivered selfACK, own currentview; exactsamecapture/delay asprior020campaign",
        "fairness": "same35actions,publicpredictor,perjobguard,finitebudget; includeallunexecutedcandidateunknowns; deterministicordersfrozeninmodelprotocol",
        "common_continuation": "v2.1 adaptive same-trayreturns andreceiving_full recovery",
        "comparison": "allfour actualjobs<=samegatepriorincumbent; allnine candidate strategiesexecutednative, no action-match substitution",
        "previous_evidence": str(previous.resolve()),
        "incumbents": {str(g): {"path": str((previous / f"gate{int(g)}/incumbent.json.gz").resolve()),
            "sha256": shared.sha(previous / f"gate{int(g)}/incumbent.json.gz")} for g in v1.GATES},
        "source_sha256": {str(s.resolve()): shared.sha(s) for s in sources},
        "claim_limits": ["minimal two-variable B4-style adaptation, notfullpaperreplica", "notrollingMPC", "notatomicagreement", "no100mscertificate"]}
    archive = output / "source_archive"; archive.mkdir()
    for s in sources: (archive / s.name).write_bytes(s.read_bytes())
    shared.write(output / "preregistered_protocol.json", p); shared.write(output / "branch_ledger.json", rows)
    return p


def worker(args):
    p = json.loads((args.output / "preregistered_protocol.json").read_text())
    if any(shared.sha(Path(f)) != h for f, h in p["source_sha256"].items()): raise ValueError("repair_native:source_drift")
    if shared.sha(args.binary) != args.expected_binary_sha256: raise ValueError("repair_native:binary_identity")
    previous = json.loads((Path(p["previous_evidence"]) / "receipt.json").read_text())
    if previous["native_binary_sha256"] != args.expected_binary_sha256 or previous["source_changed"]: raise ValueError("repair_native:incumbent_identity")
    native = load_native(args.binary)
    rows = copy.deepcopy(p["rows"]); started = time.perf_counter()
    for key, row in rows.items():
        try:
            raw = run(native, row["gate"], row["method"])
            raw["specification"] = copy.deepcopy(row)
            dst = args.output / (key + ".json.gz"); dst.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(dst, "wt", encoding="utf-8") as stream: json.dump(raw, stream, allow_nan=False)
            row.update(status=raw["summary"]["status"], summary=raw["summary"])
        except Exception: row.update(status="unknown_failed", exception=traceback.format_exc())
        shared.write(args.output / "branch_ledger.json", rows)
    comparisons = {}
    for key, row in rows.items():
        parent = p["incumbents"][str(row["gate"])]
        if shared.sha(Path(parent["path"])) != parent["sha256"]: raise ValueError("repair_native:incumbent_raw_changed")
        baseline = json.load(gzip.open(parent["path"], "rt"))["summary"]
        if row["status"] != "assessed" or baseline["status"] != "assessed": comparisons[key] = {"status": "unknown"}; continue
        times, base = row["summary"]["completion"], baseline["completion"]
        comparisons[key] = {"status": "assessed", "strict_physical_protected": all(times[j] <= base[j] for j in base),
            "gain_vs_incumbent": sum(base.values()) - sum(times.values()), "completion": times}
    changed = [f for f, h in p["source_sha256"].items() if shared.sha(Path(f)) != h]
    shared.write(args.output / "receipt.json", {"schema": p["schema"], "status": "executed" if not changed and all(r["status"] == "assessed" for r in rows.values()) else "completed_with_unknowns",
        "native_branches": 9, "comparisons": comparisons, "source_changed": changed,
        "native_binary_sha256": args.expected_binary_sha256, "wall_seconds": time.perf_counter() - started,
        "full_B4_paper_replica": False, "rolling_joint_optimizer_implemented": False, "complete_request_100ms_certified": False})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--binary", type=Path); p.add_argument("--expected-binary-sha256")
    p.add_argument("--execute", action="store_true"); p.add_argument("--worker", action="store_true")
    p.add_argument("--timeout-seconds", type=float, default=60.)
    a = p.parse_args()
    if a.worker: worker(a); return
    prepare(a.output, a.previous)
    if not a.execute: print("prepared_no_native_calls:ninebranches"); return
    if not a.binary or not a.expected_binary_sha256: p.error("exactbinaryrequired")
    cmd = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(a.output), "--previous", str(a.previous),
           "--binary", str(a.binary), "--expected-binary-sha256", a.expected_binary_sha256]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout_seconds)
        (a.output / "worker.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (a.output / "worker.stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode: shared.write(a.output / "worker_failure.json", {"status": "unknown_failed", "returncode": completed.returncode})
    except subprocess.TimeoutExpired: shared.write(a.output / "worker_failure.json", {"status": "unknown_hard_timeout"})


if __name__ == "__main__": main()
