"""Budgeted original-map R2 controls through one persistent native G31 host.

This uses the existing same-information analytic baseline without manufacturing
return requests. The source denominator never changes; disk/wall/event budgets
produce explicit censoring, not completion or physical-infeasibility claims.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .analytic_control import run_online_matching
from .native_host import audit_result, load_native
from .original_workload import (
    DEFAULT_MAP, ProxyContract, build_input, digest, return_contract_diagnostics,
    source_map, static_diagnostics, summarize_execution, verify_source_map, write_json,
)
from .validate_analytic_control import replay_input


class NativeBatchMeter:
    """Observe existing calls only; never insert or reschedule a native event.

    A batch may process physics and several requests together. Its total CPU
    must not be divided by request count and presented as per-request cost.
    result_at additionally renders offline results; that cost is separate.
    """

    def __init__(self, session):
        self.session = session
        self.batches = []

    def __getattr__(self, name):
        return getattr(self.session, name)

    def _measure(self, kind, target, *args, **kwargs):
        start_clock = self.session.physical_time
        wall, cpu = time.perf_counter(), time.process_time()
        result = getattr(self.session, kind)(target, *args, **kwargs)
        self.batches.append({"call": kind, "start_clock": start_clock, "target": target,
            "end_clock": self.session.physical_time,
            "wall_ms": 1000*(time.perf_counter()-wall), "cpu_ms": 1000*(time.process_time()-cpu),
            "status": result.get("status") if kind == "advance_to" else result.get("advance", {}).get("status"),
            "scope": "shared native event batch" if kind == "advance_to" else "native final advance plus full offline result serialization"})
        return result

    def advance_to(self, target, *args, **kwargs):
        return self._measure("advance_to", target, *args, **kwargs)

    def result_at(self, target, *args, **kwargs):
        return self._measure("result_at", target, *args, **kwargs)


def decision_identity(decision: dict) -> str:
    """Compare policy semantics independently of observation serialization.

    Pool/demand array indices are representation details. Exact population
    counts, supply identities, forecast dependencies and actual selected
    requests are policy evidence; physical events are checked separately.
    """
    payload = {key: decision[key] for key in (
        "policy", "now", "version", "forecasts", "supplies", "intents",
        "clearing_pressure_without_available_source")}
    payload["exact_waiting_count"] = decision.get("exact_waiting_count")
    payload["exact_demand_count"] = decision.get("exact_demand_count", len(decision["demands"]))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def execute(args) -> dict:
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("original_workload.py")]
    receipt = {"schema": "g31.original_online_control.v1", "status": "running",
        "source_before": {str(p): digest(p) for p in paths},
        "binary_sha256": digest(args.binary), "predictive": args.predictive,
        "respect_service_forecasts": args.service_forecasts,
        "compact_projection": args.compact_projection,
        "control_period": args.control_period, "horizon": args.horizon,
        "message_delay": args.message_delay, "demand_delay": args.demand_delay,
        "wall_budget_seconds": args.wall_budget, "max_events": args.max_events,
        "scope": "same native original-map input and lawful owner observations; analytic R2 baseline, no R1 protection certificate or main-method innovation",
        "complete_100ms_requirement_certified": False}
    write_json(args.output/"receipt.json", receipt)
    started = time.perf_counter()
    try:
        contract = ProxyContract(f"nanning-on-carrier-proxy-v1-n4-s{args.storage_berths}-t2",
                                4, args.storage_berths, 2, 1., 1., 0.,
                                "finite_berth_waiting_research_proxy")
        data, manifest, crosswalk = build_input(scale=args.scale, contract=contract,
            horizon=args.horizon, max_events=args.max_events, trace_limit=0)
        write_json(args.output/"input_manifest.json", manifest)
        profile = json.loads(DEFAULT_MAP.read_text(encoding="utf-8"))
        write_json(args.output/"source_workbooks.json", verify_source_map(profile, source_map.default_source_dir()))
        write_json(args.output/"static_diagnostics.json", static_diagnostics(data))
        write_json(args.output/"return_contract_diagnostics.json", return_contract_diagnostics(data))
        with gzip.open(args.output/"business_crosswalk.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in crosswalk:
                stream.write(json.dumps(row, sort_keys=True)+"\n")
        owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
        session = NativeBatchMeter(load_native(args.binary).NativeSession(data))
        state, submitted, compute_ms = None, [], []
        tick = 0
        reason = "common_horizon_reached"
        with (args.output/"control_steps.jsonl").open("w", encoding="utf-8") as stream:
            while True:
                target = min(tick*args.control_period, args.horizon)
                chunk_started = time.perf_counter()
                session.batches = []
                run = run_online_matching(session, owners, horizon=target,
                    predictive=args.predictive, control_period=args.control_period,
                    message_delay=args.message_delay, demand_delay=args.demand_delay,
                    respect_service_forecasts=args.service_forecasts, controller_state=state,
                    compact_projection=args.compact_projection)
                state = run["controller_state"]
                submitted.extend(run["submitted"])
                rows = []
                for record in run["control_records"]:
                    decision = record["decision"]
                    compute_ms.append(record["compute_ms"])
                    rows.append({"owner_id": record["owner_id"], "compute_ms": record["compute_ms"],
                        "compute_parts_ms": record.get("compute_parts_ms", {}),
                        "candidate_pairs": len(decision["pool"]), "supplies": len(decision["supplies"]),
                        "demands": decision.get("exact_demand_count", len(decision["demands"])),
                        "represented_demands": len(decision["demands"]),
                        "waiting": decision.get("exact_waiting_count"),
                        "demand_identity_scope": decision.get("demand_identity_scope", "all_visible_uncovered"),
                        "decision_identity": decision_identity(decision),
                        "residual_decision_identities": [decision_identity(d) for d in record["replans"]],
                        "intents": len(decision["intents"]),
                        "forecast_ledgers": dict(Counter(f["ledger"] for f in decision["forecasts"])),
                        "reply_statuses": dict(Counter(r["status"] for r in record["replies"]))})
                result = run["result"]
                summary = summarize_execution(data, result)
                stream.write(json.dumps({"tick": tick, "target": target, "status": run["status"],
                    "actual_clock": session.physical_time, "event_count": summary["native_summary"]["event_count"],
                    "observed": summary["observed"], "completed": summary["completed"], "loaded": summary["loaded"],
                    "chunk_wall_seconds": time.perf_counter()-chunk_started,
                    "publication_records": run.get("publication_records", []),
                    "native_batches": session.batches,
                    "owner_computations": rows, "submitted": run["submitted"]})+"\n")
                stream.flush()
                if run["status"] != "reached":
                    reason = "native_event_budget_censored"
                    break
                if target == args.horizon:
                    break
                if time.perf_counter()-started >= args.wall_budget:
                    reason = "wall_budget_censored_at_completed_control_boundary"
                    break
                tick += 1
        receipt["stop_reason"] = reason
        receipt["status"] = "reached" if summary["horizon_reached"] else "censored"
        receipt["offline_final_state_sha256"] = session.offline_state_sha256()
        receipt["control_compute_ms"] = {"count": len(compute_ms), "max": max(compute_ms, default=0.),
            "sum": sum(compute_ms), "over_100ms": sum(value > 100 for value in compute_ms),
            "scope": run["timing_scope"]}
        write_json(args.output/"summary.json", summary)
        write_json(args.output/"event_audit.json", audit_result(replay_input(data, submitted), result))
        write_json(args.output/"submitted_requests.json", submitted)
        with gzip.open(args.output/"controller_state.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(state, stream)
        with gzip.open(args.output/"business_results.jsonl.gz", "wt", encoding="utf-8") as stream:
            for job in result["jobs"]:
                stream.write(json.dumps(job)+"\n")
        with gzip.open(args.output/"physical_events.jsonl.gz", "wt", encoding="utf-8") as stream:
            for event in result["receipts"]:
                stream.write(json.dumps(event)+"\n")
        # Native checkpoints remain process-bound; never label the controller
        # JSON as an independently restorable physical checkpoint.
        receipt["continuation_boundary"] = {"physical_time": session.physical_time,
            "native_session_persisted": False, "rerun_required_after_process_exit": True}
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["wall_seconds"] = time.perf_counter()-started
    receipt["source_changed"] = [str(p) for p in paths if digest(p) != receipt["source_before"][str(p)]]
    write_json(args.output/"receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--control-period", type=float, default=300.)
    parser.add_argument("--message-delay", type=float, default=2.)
    parser.add_argument("--demand-delay", type=float, default=.5)
    parser.add_argument("--max-events", type=int, default=100000)
    parser.add_argument("--storage-berths", type=int, default=4)
    parser.add_argument("--wall-budget", type=float, default=120.)
    parser.add_argument("--predictive", action="store_true")
    parser.add_argument("--service-forecasts", action="store_true")
    parser.add_argument("--compact-projection", action="store_true",
                        help="Use exact native FIFO projection; all physical jobs and offered denominators remain intact.")
    args = parser.parse_args()
    receipt = execute(args)
    print(json.dumps(receipt, indent=2))
    return int(receipt["status"] == "failed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
