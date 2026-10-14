"""Frozen009 read-only method timing; reconstruct the original recorded policy."""
from pathlib import Path
import gzip
import hashlib
import json
import os
import statistics
import sys
import time
import traceback
import types

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
BASE = ROOT / "outputs/experiments/g31_ics_long_term_20261013/p2_original_2x_reactive_compact_H86400_009_001"
BINARY = ROOT / "build_lt_session_009/python/czr005_circulation.cp311-win_amd64.pyd"
BOUNDARY = 76500.0
EXPECTED_BINARY = "fbc97e38552c03af81c2c6d896a2d4d67fcf8c7eefd5a5319ef4651b37d3daea"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def identity(decision):
    payload = {key: decision[key] for key in ("policy", "now", "version", "forecasts", "supplies", "intents", "clearing_pressure_without_available_source")}
    payload["exact_waiting_count"] = decision.get("exact_waiting_count")
    payload["exact_demand_count"] = decision.get("exact_demand_count", len(decision["demands"]))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def main():
    started = time.perf_counter()
    baseline = json.loads((BASE / "receipt.json").read_text())
    sources = {name: Path(name) for name in baseline["source_before"]}
    before = {name: sha(path) for name, path in sources.items()}
    receipt = {"schema": "g31.frozen009_projection_microprofile.v1", "status": "running", "boundary": BOUNDARY,
               "source_before": before, "binary_sha256": sha(BINARY), "wall_budget_seconds": 240,
               "source_freeze": "analytic source bytes compiled from saved copy; native009 frozen binary; no implementation mutation",
               "scope": "read-only method microtiming at actual original 2x policy boundary; not full100ms certification"}
    write("receipt.json", receipt)
    try:
        assert before == baseline["source_before"], "baseline source changed before freezing"
        assert receipt["binary_sha256"] == EXPECTED_BINARY
        for name, path in sources.items():
            (OUT / ("frozen_" + path.name)).write_bytes(path.read_bytes())
        name = "scripts.experiments.g31_ics_circulation.analytic_control"
        module = types.ModuleType(name)
        module.__package__ = "scripts.experiments.g31_ics_circulation"
        module.__file__ = str(OUT / "frozen_analytic_control.py")
        sys.modules[name] = module
        exec(compile((OUT / "frozen_analytic_control.py").read_bytes(), module.__file__, "exec"), module.__dict__)
        from scripts.experiments.g31_ics_circulation.original_workload import ProxyContract, build_input
        from scripts.experiments.g31_ics_circulation.native_host import load_native
        data, manifest, _ = build_input(scale=2, contract=ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2", 4, 4, 2, 1., 1., 0., "finite_berth_waiting_research_proxy"), horizon=86400, max_events=160000, trace_limit=0)
        assert manifest["input_sha256"] == json.loads((BASE / "input_manifest.json").read_text())["input_sha256"]
        write("input_identity.json", manifest)
        owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
        native = load_native(BINARY)
        session = native.NativeSession(data)
        print(json.dumps({"phase": "reconstruct", "owners": owners, "offered": len(data["jobs"])}), flush=True)
        run = module.run_online_matching(session, owners, horizon=BOUNDARY, predictive=False, control_period=900., message_delay=2., demand_delay=.5, compact_projection=True)
        assert run["status"] == "reached"
        old = [json.loads(line) for line in (BASE / "control_steps.jsonl").read_text().splitlines()]
        expected = {(float(row["target"]), x["owner_id"]): x for row in old if row["target"] <= BOUNDARY for x in row["owner_computations"]}
        matches = []
        for record in run["control_records"]:
            decision = record["decision"]
            key = (float(decision["now"]), record["owner_id"])
            prior = expected[key]
            assert identity(decision) == prior["decision_identity"], (key, "policy identity mismatch")
            assert [identity(d) for d in record["replans"]] == prior["residual_decision_identities"]
            matches.append({"now": key[0], "owner_id": key[1], "decision_identity": identity(decision)})
        assert len(matches) == len(expected)
        expected_events = [json.loads(line) for line in gzip.open(BASE / "physical_events.jsonl.gz", "rt", encoding="utf-8") if line.strip()]
        expected_events = [row for row in expected_events if row["time"] <= BOUNDARY]
        assert run["result"]["receipts"] == expected_events, "physical receipts differ at boundary"
        write("policy_identity_check.json", {"status": "passed", "decisions": len(matches), "physical_receipts": len(expected_events), "all_recorded_actions_and_physical_prefix_equal": True})
        state_before = session.offline_state_sha256()
        print(json.dumps({"phase": "read_only_samples", "reconstruction_seconds": time.perf_counter()-started, "physical_clock": session.physical_time}), flush=True)
        samples = []
        # First-after-reconstruction is reported separately; it is not called
        # a process-cold query because reconstruction already observed owners.
        for repeat in range(10):
            assert time.perf_counter()-started < 240, "microprofile wall budget exhausted"
            for owner in owners:
                functions = [("observe_control", lambda: session.observe_control(owner)),
                             ("demand_signature", lambda: session.demand_signature(owner)),
                             ("observe_full", lambda: session.observe(owner))]
                if repeat % 2:
                    functions.reverse()
                for method, call in functions:
                    wall, cpu = time.perf_counter(), time.process_time()
                    result = call()
                    elapsed, used = 1000*(time.perf_counter()-wall), 1000*(time.process_time()-cpu)
                    row = {"repeat": repeat, "owner_id": owner, "method": method, "wall_ms": elapsed, "cpu_ms": used,
                           "temperature": "first_after_reconstruction" if repeat == 0 else "repeated_read_only"}
                    if method == "observe_control":
                        cp = result["control_projection"]
                        row.update(waiting=cp["exact_waiting_count"], candidate_limit=cp["candidate_limit"], represented=sum(len(g["jobs"]) for g in cp["waiting_groups"]), serialized_jobs=len(result["jobs"]), local_trays=len(result["trays"]))
                    elif method == "demand_signature":
                        row.update(waiting=result["waiting_count"], signature=result["sha256"])
                    else:
                        row.update(serialized_jobs=len(result["jobs"]), remote_snapshot_jobs=sum(len(m.get("jobs", [])) for m in result["delivered_messages"]))
                    samples.append(row)
        assert session.offline_state_sha256() == state_before, "read-only query mutated native state"
        write("samples.json", samples)
        summary = []
        for owner in owners:
            for method in ("observe_control", "demand_signature", "observe_full"):
                values = [row["wall_ms"] for row in samples if row["owner_id"] == owner and row["method"] == method]
                summary.append({"owner_id": owner, "method": method, "n": len(values), "first_ms": values[0], "min_ms": min(values), "median_ms": statistics.median(values), "mean_ms": statistics.mean(values), "max_ms": max(values)})
        write("summary.json", summary)
        receipt.update(status="passed", native_state_unchanged=True, state_sha256=state_before,
                       policy_decisions_checked=len(matches), physical_receipts_checked=len(expected_events), sample_count=len(samples), timings=summary)
    except Exception:
        receipt.update(status="failed", traceback=traceback.format_exc())
        raise
    finally:
        receipt["source_after"] = {name: sha(path) for name, path in sources.items()}
        receipt["source_changed"] = [name for name, value in before.items() if receipt["source_after"][name] != value]
        receipt["wall_seconds"] = time.perf_counter()-started
        write("receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "wall_seconds": receipt["wall_seconds"], "samples": receipt.get("sample_count")}), flush=True)


if __name__ == "__main__":
    main()
