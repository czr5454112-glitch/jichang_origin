"""Independent small-file completion audit for the accepted 480 base cells.

No runner imports, simulation, process operations, or large native archives.
Only this new review JSON is written; original evidence is read-only.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PLAN = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v6/plan.json"
PLAN_SHA = "7a4369b09efb8b2935a7197d6919375be730ffb5ee17a8cad55718fcdb262daf"
POOL = ROOT / "outputs/runtime/feng_paper_suite_20260907/orchestration/20260907T103503Z_c3cdea603a/status.json"
G31 = "G31_S4_ADVERTISED_FAULT_REPAIR_V1"
TARAU = "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY"
HCA = "HCA_TIME_LABEL_REPAIR_V3"
DH = "FENG_DH_PAPER_SUITE_V6"
METHODS = (G31, HCA, DH, TARAU)
SEEDS = (104729, 130363, 155921, 181081, 205759, 232003, 257053, 283303, 308081, 333667)
COORD = ("map", "load_factor", "speed_mps", "method", "seed")
CACHE = {}
HASHES = {}


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def read(path, expected=None):
    path = Path(path).resolve(strict=True)
    key = str(path)
    if key not in CACHE:
        data = path.read_bytes()
        CACHE[key] = json.loads(data.decode("utf-8-sig"))
        HASHES[key] = hashlib.sha256(data).hexdigest()
    if expected is not None:
        need(HASHES[key] == expected, f"SHA differs: {path}")
    return CACHE[key]


def sha(path):
    read(path)
    return HASHES[str(Path(path).resolve())]


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def run():
    output = Path(__file__).with_name("verification.json")
    need(not output.exists(), "refusing to overwrite review evidence")
    plan = read(PLAN, PLAN_SHA)
    pool = read(POOL)
    need(pool["plan_sha256"] == PLAN_SHA and Path(pool["plan_path"]).resolve() == PLAN, "pool plan differs")
    need(pool["status"] == "COMPLETE", "base pool not complete")
    for field in ("selected_count", "finished_count", "accepted_count"):
        need(pool[field] == 480, f"pool {field} differs")
    need(not pool["active_cell_ids"] and not pool["not_started_cell_ids"], "active/not-started base cells remain")
    need(pool["stopped_dispatching_after_failure"] is False and pool["campaign_lock_retained"] is False, "pool did not finish cleanly")
    cells = [c for c in plan["cells"] if c["family"] == "base"]
    expected = set(itertools.product(("map2", "nanning"), (1., 2.), (1.5, 2.5, 3.), METHODS, SEEDS))
    coordinates = [tuple(c[k] for k in COORD) for c in cells]
    need(len(cells) == len(set(coordinates)) == 480 and set(coordinates) == expected, "base grid mismatch")
    need(all(c["scenario_index"] == 0 for c in cells), "fault scenario in base grid")
    ids = {c["cell_id"] for c in cells}
    need(len(ids) == 480 and len(pool["selected_cell_ids"]) == 480 and set(pool["selected_cell_ids"]) == ids, "pool selection mismatch")
    records = {c["cell_id"]: c for c in pool["cells"]}
    need(len(pool["cells"]) == len(records) == 480 and set(records) == ids, "pool record omission/duplication")
    need(all(r["status"] in ("COMPLETE", "REUSED_VERIFIED") for r in records.values()), "failed base record")
    checked = []
    groups = defaultdict(list)
    for cell in cells:
        name = cell["cell_id"]
        receipt = records[name]
        for field in ("cell_id", "method", "spec_sha256", "runner_sha256", "output_dir"):
            need(receipt[field] == cell[field], f"receipt {field} differs: {name}")
        child_receipt = POOL.parent / "cells" / name / "status.json"
        need(read(child_receipt) == receipt, f"pool/child receipt differs: {name}")
        spec = read(cell["spec_path"], cell["spec_sha256"])
        for field in COORD:
            need(spec[field] == cell[field], f"spec {field} differs: {name}")
        need(spec["family"] == "base" and spec["timing_policy"] == "full_population_only"
             and spec.get("horizon_seconds", spec.get("fixed_horizon_seconds")) == 98259, "spec timing/scope differs")
        identity = read(spec["workload_identity_path"], spec["workload_identity_sha256"])
        for field in ("map", "load_factor", "seed"):
            need(identity[field] == cell[field], f"workload {field} differs")
        out = Path(cell["output_dir"])
        need(not any((out / n).exists() for n in ("run.lock", "execution.lock", ".run_lock", "run_failure.json")), "unfinished/failed native evidence")
        result_path, status_path = out / "normalized_result.json", out / "runner_status.json"
        result = read(result_path, receipt["normalized_result_sha256"])
        status = read(status_path)
        need(result["status"] == "COMPLETE" and status["status"].upper() == "COMPLETE", "terminal envelope missing")
        for field in ("method", "map", "load_factor", "seed"):
            need(result[field] == cell[field], f"normalized {field} differs: {name}")
        need(result["workload_identity_sha256"] == spec["workload_identity_sha256"], "normalized workload differs")
        method = cell["method"]
        if method in (G31, TARAU):
            need(status["normalized_result_sha256"] == sha(result_path), "CPP result SHA differs")
            need(result["spec"]["speed_mps"] == cell["speed_mps"], "CPP speed differs")
            for field in ("runner_sha256", "protocol_sha256", "binary_sha256", "workload_identity_sha256"):
                need(result["provenance"][field] == (cell[field] if field == "runner_sha256" else spec[field]), "CPP provenance differs")
            for field in ("raw_sha256", "canonical_sha256", "map_sha256"):
                need(result["provenance"][field] == identity[field], "CPP input differs")
            a = result["population_audit"]
            need(a["status"] == "PASS" and a["gates"] and all(v is True for v in a["gates"].values()), "CPP population gate failed")
            full, n, done = a["full_population_complete"], a["raw_bag_count"], a["completed_raw_bag_count"]
            segments, completed_segments = a["segment_count"], a["completed_segment_count"]
            need(a["timing_eligible"] is full, "CPP timing qualification differs")
            timings = []
            for field in ("primary_timing", "native_timing"):
                t = a[field]
                need((t is not None) is full, "CPP incomplete population has timing")
                if full:
                    need(t["count"] == n, "CPP timing population count differs")
                    timings.extend(t[k] for k in ("min", "mean", "max"))
        else:
            need(result["speed_mps"] == cell["speed_mps"] and result["family"] == "base", "Java speed/family differs")
            key = "run_spec_sha256" if method == HCA else "spec_sha256"
            runner_key = "python_runner_sha256" if method == HCA else "runner_sha256"
            need(result[key] == status[key] == cell["spec_sha256"], "Java spec SHA differs")
            need(status[runner_key] == cell["runner_sha256"] and status["returncode"] == 0, "Java runner identity/native exit differs")
            need(status["protocol_sha256"] == spec["protocol_sha256"], "Java protocol differs")
            need(result["survivor_timing_used"] is False, "survivor THT used")
            full, m = result["full_population_complete"], result["metrics"]
            done = m["completed_raw_bag_count"]
            if method == HCA:
                a = result["population_audit"]
                need(a["status"] == "PASS" and a["full_population_complete"] is full, "HCA audit differs")
                n, segments, completed_segments = result["raw_bag_denominator"], result["segment_denominator"], a["completed_segment_count"]
                prefixes = ("tht_scheduled_release", "tht_admission")
                for k in ("raw", "canonical", "map"):
                    need(result[f"workload_{k}_sha256"] == status["inputs"][k]["sha256"] == identity[f"{k}_sha256"], "HCA input differs")
            else:
                need(result["audit_status"] == "PASS", "DH audit failed")
                a = read(out / "population_audit.json")
                need(a["status"] == "PASS" and a["metrics"] == m and a["full_population_complete"] is full, "DH standalone audit differs")
                n, segments, completed_segments = m["raw_bag_denominator"], a["segment_count"], m["completed_segment_count"]
                prefixes = ("tht_D", "tht_native")
            timings = [m[f"{prefix}_{stat}_seconds"] for prefix in prefixes for stat in ("min", "mean", "max")]
            if not full:
                formal = {k: v for k, v in m.items() if k.startswith(("tht_", "population_latency_"))}
                need(all(v is None for v in timings) and all(v is None for v in formal.values()), "incomplete population contains formal THT")
        need(type(full) is bool and receipt["full_population_complete"] is full, "receipt/full flag differs")
        need(n == identity["raw_bag_count"] and segments == identity["segment_count"], "population denominator differs")
        need(0 <= done <= n and 0 <= completed_segments <= segments and full == (done == n) == (completed_segments == segments), "full population count inconsistent")
        if full:
            need(len(timings) == 6 and all(finite(v) for v in timings), "complete population missing finite timing")
        entry = {"cell_id": name, **{k: cell[k] for k in COORD}, "receipt_status": receipt["status"],
                 "normalized_sha256": sha(result_path), "runner_status_sha256": sha(status_path),
                 "spec_sha256": cell["spec_sha256"], "workload_identity_sha256": spec["workload_identity_sha256"],
                 "full_population_complete": full, "raw_bags": n, "completed_raw_bags": done,
                 "segment_count": segments, "completed_segment_count": completed_segments,
                 "formal_timing_status": "FULL_POPULATION_FINITE" if full else "ALL_FORMAL_THT_NULL"}
        checked.append(entry)
        groups[tuple(cell[k] for k in ("map", "load_factor", "speed_mps", "method"))].append(entry)
    need(len(groups) == 48 and all(tuple(sorted(r["seed"] for r in v)) == SEEDS for v in groups.values()), "group seed coverage differs")
    summary = [{**dict(zip(("map", "load_factor", "speed_mps", "method"), k)), "accepted": len(v),
                "full_population": sum(r["full_population_complete"] for r in v),
                "incomplete_population": sum(not r["full_population_complete"] for r in v)} for k, v in sorted(groups.items())]
    result = {"schema": "czr005.paper_suite.base480_independent_completion_review.v1", "status": "PASS",
              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": {"path": str(Path(__file__).resolve()), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "plan": {"path": str(PLAN), "sha256": sha(PLAN)}, "pool": {"path": str(POOL), "sha256": sha(POOL)},
              "accepted_count": 480, "coordinate_count": 480, "duplicate_or_missing_or_failed_count": 0,
              "pool_record_statuses": dict(Counter(r["status"] for r in records.values())),
              "full_population_cells": sum(r["full_population_complete"] for r in checked),
              "incomplete_population_cells_with_all_formal_tht_null": sum(not r["full_population_complete"] for r in checked),
              "group_count": 48, "groups": summary, "cells": checked,
              "native_simulations_invoked": 0, "large_native_archives_opened": 0,
              "scope": "Base480 coordinate, frozen identity, accepted result SHA, terminal population qualification and THT-null audit; not a new native population replay or exhaustive physical proof. Remaining fault96 is outside this completion claim."}
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "accepted_count", "full_population_cells", "incomplete_population_cells_with_all_formal_tht_null")}, ensure_ascii=False))


if __name__ == "__main__":
    run()
