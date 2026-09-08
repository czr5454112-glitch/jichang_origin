"""Independent small-file completion audit for the accepted 576 registered cells.

No runner imports, simulation, process operations, or large native archives.
Only this new review JSON is written; original evidence is read-only.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PLAN = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v6/plan.json"
PLAN_SHA = "7a4369b09efb8b2935a7197d6919375be730ffb5ee17a8cad55718fcdb262daf"
BASE_POOL = ROOT / "outputs/runtime/feng_paper_suite_20260907/orchestration/20260907T103503Z_c3cdea603a/status.json"
G31 = "G31_S4_ADVERTISED_FAULT_REPAIR_V1"
TARAU = "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY"
HCA = "HCA_TIME_LABEL_REPAIR_V3"
DH = "FENG_DH_PAPER_SUITE_V6"
METHODS = (G31, HCA, DH, TARAU)
SEEDS = (104729, 130363, 155921, 181081, 205759, 232003, 257053, 283303, 308081, 333667)
COORD = ("map", "load_factor", "speed_mps", "method", "seed")
FAULT_POOL = ROOT / "outputs/runtime/feng_paper_suite_20260907/orchestration/20260908T042131Z_9ddd661288/status.json"
MASTER = ROOT / "outputs/runtime/feng_paper_suite_20260907/campaign_master/20260907T103048Z_87ca6ab5b9/status.json"
SNAPSHOT = ROOT / "outputs/reports/feng_paper_suite_20260907/campaign_20260907T103048Z_87ca6ab5b9/snapshot.json"
SNAPSHOT_SHA = "345b5d7b1fafebc598ec1ca927c19125eab8b2339ed32e27c6bb51659281ebb5"
OLD_SNAPSHOT = ROOT / "outputs/reports/feng_paper_suite_20260907/20260908T043341Z_base480_complete_v2/snapshot.json"
OLD_SNAPSHOT_SHA = "fb3c0d96f4b7ec84c8f17aaf5bb97d2b04ffc036b7f38eda2f34a8356afeff0f"
TIMINGS = tuple(f"tht_{clock}_{stat}_seconds" for clock in ("D", "native") for stat in ("min", "mean", "max"))
METRICS = ("TH", "completion_rate", "success_std_rate", "success_paper_literal_rate", *TIMINGS)
GRID_FIELDS = ("family", "map", "load_factor", "speed_mps", "scenario_index", "seed", "method")
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


def file_sha(path):
    path = Path(path).resolve(strict=True)
    key = str(path)
    if key not in HASHES:
        HASHES[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return HASHES[key]


def same(actual, expected, label):
    if expected is None:
        need(actual is None, label)
    elif finite(expected):
        need(finite(actual) and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10), label)
    else:
        need(actual == expected, label)


def expected_grid():
    base = set(itertools.product(("base",), ("map2", "nanning"), (1., 2.),
                                 (1.5, 2.5, 3.), (0,), SEEDS, METHODS))
    fault = set(itertools.product(("all_day_fault",), ("map2", "nanning"), (1., 2.),
                                  (2.5,), (1, 2, 9, 14), SEEDS[:3], (G31, HCA)))
    return base | fault


def prepare():
    plan = read(PLAN, PLAN_SHA)
    snapshot = read(SNAPSHOT, SNAPSHOT_SHA)
    old = read(OLD_SNAPSHOT, OLD_SNAPSHOT_SHA)
    master = read(MASTER)
    need(master["status"] == "COMPLETE" and master["plan_sha256"] == PLAN_SHA, "master not final V6")
    need(master["report"]["status"] == "COMPLETE" and master["report"]["returncode"] == 0
         and master["report"]["snapshot"]["sha256"] == SNAPSHOT_SHA, "master report receipt differs")
    need(master["expected_cells"] == 576 and master["family_counts"] == {"base": 480, "all_day_fault": 96}, "master scope differs")
    need(master["execution_order"] == ["base", "all_day_fault"], "execution order differs")
    cells = plan["cells"]
    coords = [tuple(c[k] for k in GRID_FIELDS) for c in cells]
    need(len(cells) == len(set(coords)) == 576 and set(coords) == expected_grid(), "plan coordinate set differs")
    need(len({c["cell_id"] for c in cells}) == 576, "duplicate plan cell id")
    need(snapshot["status"] == "COMPLETE" and snapshot["plan_sha256"] == PLAN_SHA, "snapshot status/plan differs")
    need(snapshot["expected_cells"] == snapshot["observed_cell_rows"] == 576
         and snapshot["expected_pairs"] == snapshot["observed_pair_rows"] == 408, "snapshot row counts differ")
    need(snapshot["cell_state_counts"] == {"COMPLETE": 576, "FAILED": 0, "INVALID": 0,
         "MISSING": 0, "POSTPROCESSING": 0, "RUNNING": 0}, "snapshot nonaccepted state")
    need(snapshot["pair_input_mismatch_count"] == 0, "pair input mismatch")
    rows = snapshot["cells"]
    need(len(rows) == 576 and len({r["cell_id"] for r in rows}) == 576
         and {tuple(r[k] for k in GRID_FIELDS) for r in rows} == expected_grid(), "snapshot coordinates differ")
    need(all(r["cell_state"] == "COMPLETE" and r["terminal_result_accepted"] is True
             and r["error"] is None and not r["postprocessing_pending"] for r in rows), "unaccepted snapshot cell")
    records, pools = {}, {"base": BASE_POOL, "all_day_fault": FAULT_POOL}
    for family, count in (("base", 480), ("all_day_fault", 96)):
        pool = read(pools[family])
        need(pool["plan_sha256"] == PLAN_SHA and Path(pool["plan_path"]).resolve() == PLAN, "pool plan differs")
        need(pool["status"] == "COMPLETE", "pool not COMPLETE")
        need(all(pool[k] == count for k in ("selected_count", "finished_count", "accepted_count")), "pool count differs")
        need(not pool["active_cell_ids"] and not pool["not_started_cell_ids"]
             and pool["stopped_dispatching_after_failure"] is False and pool["campaign_lock_retained"] is False, "pool not cleanly terminal")
        ids = {c["cell_id"] for c in cells if c["family"] == family}
        need(len(pool["selected_cell_ids"]) == count and set(pool["selected_cell_ids"]) == ids, "pool selection differs")
        local = {r["cell_id"]: r for r in pool["cells"]}
        need(len(pool["cells"]) == len(local) == count and set(local) == ids, "pool receipts missing or duplicated")
        need(all(r["status"] in ("COMPLETE", "REUSED_VERIFIED") for r in local.values()), "pool failed receipt")
        records.update(local)
        need(snapshot["family_progress"][family]["status"] == "COMPLETE"
             and snapshot["family_progress"][family]["accepted_cells"] == count, "family progress differs")
    return plan, snapshot, cells, records, pools, old


def read_csv(path):
    file_sha(path)
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value):
    return None if value == "NA" else float(value)


def audit_tables_and_groups(snapshot):
    rows = snapshot["cells"]
    by_id = {r["cell_id"]: r for r in rows}
    csv_rows = read_csv(SNAPSHOT.parent / "cells.csv")
    need(len(csv_rows) == 576 and len({r["cell_id"] for r in csv_rows}) == 576, "cells.csv row coverage differs")
    for row in csv_rows:
        source = by_id[row["cell_id"]]
        need(set(source).issubset(row), "cells.csv columns missing")
        need(all(row[k] == "" for k in set(row)-set(source)), "cells.csv extra nonempty field")
        need(all(row[k] == ("NA" if v is None else str(v)) for k, v in source.items()), "cells.csv value differs")
    pairs = read_csv(SNAPSHOT.parent / "paired.csv")
    need(len(pairs) == 408, "paired.csv count differs")
    seen = set()
    pair_groups = defaultdict(list)
    method_groups = defaultdict(list)
    group_fields = tuple(k for k in GRID_FIELDS if k not in ("seed", "method"))
    for row in rows:
        method_groups[tuple(row[k] for k in (*group_fields, "method"))].append(row)
    for pair in pairs:
        g, b = by_id[pair["g31_cell_id"]], by_id[pair["baseline_cell_id"]]
        key = tuple(b[k] for k in GRID_FIELDS)
        need(key not in seen, "duplicate seed pair")
        seen.add(key)
        need(g["method"] == pair["reference"] == G31 and b["method"] == pair["baseline"] != G31, "pair method differs")
        need(pair["pair_status"] == "COMPLETE", "pair not complete")
        for k in (*group_fields, "seed"):
            need(g[k] == b[k] and pair[k] == str(g[k]), "pair coordinate differs")
        for k in ("raw_sha256", "canonical_sha256", "map_sha256", "raw_bag_count", "segment_count",
                  "horizon_seconds", "affected_edges_json", "fault_mapping_sha256", "input_signature_sha256"):
            need(g[k] == b[k], "pair common input differs: " + k)
        full = g["full_population_complete"] and b["full_population_complete"]
        need(pair["tht_pair_eligible"] == str(full), "pair THT qualification differs")
        for metric in METRICS:
            gv, bv = (g[metric], b[metric]) if metric not in TIMINGS or full else (None, None)
            same(number(pair["g31_" + metric]), gv, "pair G31 metric differs")
            same(number(pair["baseline_" + metric]), bv, "pair baseline metric differs")
            benefit = None if gv is None else bv-gv if metric in TIMINGS else gv-bv
            same(number(pair["g31_benefit_" + metric]), benefit, "pair benefit differs")
            pct = benefit/bv*100 if benefit is not None and bv != 0 else None
            same(number(pair["g31_benefit_" + metric + "_percent"]), pct, "pair percent differs")
            if metric.endswith("_rate"):
                same(number(pair["g31_benefit_" + metric + "_pp"]), benefit*100, "pair percentage point differs")
        pair_groups[tuple(b[k] for k in (*group_fields, "method"))].append(pair)
    need(seen == {c for c in expected_grid() if c[-1] != G31}, "paired coordinate coverage differs")
    need(len(method_groups) == 80 and len(pair_groups) == 52, "derived groups differ")
    need(Counter(k[0] for k in method_groups) == {"base": 48, "all_day_fault": 32}, "method family group counts differ")
    need(Counter(k[0] for k in pair_groups) == {"base": 36, "all_day_fault": 16}, "paired family group counts differ")
    need(len(snapshot["method_groups"]) == 80 and len(snapshot["paired_groups"]) == 52, "snapshot group counts differ")
    for paired, group_map, items in ((False, method_groups, snapshot["method_groups"]),
                                    (True, pair_groups, snapshot["paired_groups"])):
        group_seen = set()
        for item in items:
            key = tuple(item[k] for k in group_fields) + (item["baseline" if paired else "method"],)
            need(key not in group_seen and key in group_map, "group duplicate/mismatch")
            group_seen.add(key)
            group = group_map[key]
            seeds = SEEDS if key[0] == "base" else SEEDS[:3]
            need(sorted(int(r["seed"]) for r in group) == list(seeds) and item["registered_seeds"] == list(seeds), "group seed set differs")
            n = len(seeds)
            full_n = sum(r["tht_pair_eligible"] == "True" if paired else r["full_population_complete"] for r in group)
            need(item["complete_seed_count"] == item["expected_seed_count"] == n
                 and item["tht_eligible_seed_count"] == full_n and item["status"] == f"COMPLETE_{n}_SEEDS", "group eligibility differs")
            for metric in METRICS:
                eligible = metric not in TIMINGS or full_n == n
                if not paired:
                    expected = math.fsum(r[metric] for r in group)/n if eligible else None
                    same(item[metric], expected, "method group mean differs")
                else:
                    actual = item["metrics"][metric]
                    need(actual["eligible"] is eligible, "paired group qualification differs")
                    if not eligible:
                        need(all(v is None for k, v in actual.items() if k != "eligible"), "ineligible group contains survivor statistics")
                        continue
                    gv = math.fsum(number(r["g31_" + metric]) for r in group)/n
                    bv = math.fsum(number(r["baseline_" + metric]) for r in group)/n
                    benefits = [number(r["g31_benefit_" + metric]) for r in group]
                    avg = math.fsum(benefits)/n
                    for k, v in {"g31_mean": gv, "baseline_mean": bv, "mean_benefit": avg,
                                 "benefit_percent_of_means": avg/bv*100 if bv else None,
                                 "wins": sum(v > 1e-9 for v in benefits), "ties": sum(abs(v) <= 1e-9 for v in benefits),
                                 "losses": sum(v < -1e-9 for v in benefits)}.items():
                        same(actual[k], v, "paired group value differs: " + k)
    return {"cell_rows": 576, "seed_pair_rows": 408, "method_groups": 80, "paired_groups": 52,
            "method_groups_by_family": {"base": 48, "all_day_fault": 32},
            "paired_groups_by_family": {"base": 36, "all_day_fault": 16}}


def finish_review(plan, snapshot, old, checked, records, groups, output):
    table_counts = audit_tables_and_groups(snapshot)
    old_base = {r["cell_id"]: r for r in old["cells"] if r["family"] == "base"}
    new_base = {r["cell_id"]: r for r in snapshot["cells"] if r["family"] == "base"}
    need(len(old_base) == len(new_base) == 480 and old_base == new_base, "earlier base480 rows changed")
    for key in ("method_groups", "paired_groups"):
        need([r for r in old[key] if r["family"] == "base"] == [r for r in snapshot[key] if r["family"] == "base"], "earlier base group changed")
    old_pair_rows = [r for r in read_csv(OLD_SNAPSHOT.parent / "paired.csv") if r["family"] == "base"]
    new_pair_rows = [r for r in read_csv(SNAPSHOT.parent / "paired.csv") if r["family"] == "base"]
    need(len(old_pair_rows) == 360 and old_pair_rows == new_pair_rows, "earlier base paired.csv changed")
    for descriptor in snapshot["output_files"]:
        p = SNAPSHOT.parent / descriptor["path"]
        need(file_sha(p) == descriptor["sha256"] and p.stat().st_size == descriptor["bytes"], "snapshot output file hash differs")
    family = {}
    for name in ("base", "all_day_fault"):
        cells = [r for r in checked if r["family"] == name]
        full = sum(r["full_population_complete"] for r in cells)
        family[name] = {"accepted_cells": len(cells), "full_population_cells": full,
                        "incomplete_population_cells_with_all_six_tht_null": len(cells)-full,
                        "receipt_statuses": dict(Counter(r["receipt_status"] for r in cells))}
        need(snapshot["family_progress"][name]["full_population_cells"] == full
             and snapshot["family_progress"][name]["incomplete_population_cells"] == len(cells)-full, "family counts differ")
    full = sum(r["full_population_complete"] for r in checked)
    need(full == snapshot["full_population_cell_count"] and len(checked)-full == snapshot["censored_population_cell_count"], "total population qualification counts differ")
    result = {"schema": "czr005.paper_suite.final576_independent_completion_review.v1", "status": "PASS",
              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": {"path": str(Path(__file__).resolve()), "sha256": file_sha(__file__)},
              "plan": {"path": str(PLAN), "sha256": sha(PLAN)},
              "snapshot": {"path": str(SNAPSHOT), "sha256": sha(SNAPSHOT)},
              "master": {"path": str(MASTER), "sha256": sha(MASTER)},
              "pools": [{"path": str(p), "sha256": sha(p)} for p in (BASE_POOL, FAULT_POOL)],
              "accepted_count": len(checked), "coordinate_count": len(checked),
              "missing_or_duplicate_or_failed_or_invalid_or_input_mismatch_count": 0,
              "full_population_cells": full,
              "incomplete_population_cells_with_all_six_tht_null": len(checked)-full,
              "family_counts": family, "table_checks": table_counts,
              "prior_base_comparison": {"path": str(OLD_SNAPSHOT), "sha256": sha(OLD_SNAPSHOT),
                 "all_fields_identical_cell_count": 480, "identical_seed_pair_rows": 360,
                 "identical_method_groups": 48, "identical_paired_groups": 36},
              "cells": checked,
              "checked_small_file_hashes": [{"path": k, "sha256": v} for k, v in sorted(HASHES.items())],
              "native_simulations_invoked": 0, "large_native_archives_opened": 0,
              "scope": "Exact registered reduced576 metadata acceptance, current source/spec/identity/result/outer receipt SHA, formal THT qualification, scalar table arithmetic and unchanged prior base480. No native rerun or complete native archive decompression; this PASS is not an exhaustive physical proof or a full16-fault paper reproduction."}
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "accepted_count", "full_population_cells", "incomplete_population_cells_with_all_six_tht_null", "family_counts", "table_checks")}, ensure_ascii=False))


def run():
    output = Path(__file__).with_name("verification.json")
    need(not output.exists(), "refusing to overwrite review evidence")
    plan, snapshot, cells, records, pool_paths, old_snapshot = prepare()
    snapshot_rows = {r["cell_id"]: r for r in snapshot["cells"]}
    checked = []
    groups = defaultdict(list)
    for cell in cells:
        name = cell["cell_id"]
        receipt = records[name]
        for field in ("cell_id", "method", "spec_sha256", "runner_sha256", "output_dir"):
            need(receipt[field] == cell[field], f"receipt {field} differs: {name}")
        child_receipt = pool_paths[cell["family"]].parent / "cells" / name / "status.json"
        need(read(child_receipt) == receipt, f"pool/child receipt differs: {name}")
        spec = read(cell["spec_path"], cell["spec_sha256"])
        for field in GRID_FIELDS:
            actual = spec.get(field, 0) if field == "scenario_index" and cell["family"] == "base" else spec[field]
            need(actual == cell[field], f"spec {field} differs: {name}")
        need(spec["family"] == cell["family"] and spec["timing_policy"] == "full_population_only"
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
        need(file_sha(cell["runner_path"]) == cell["runner_sha256"], "runner source SHA differs")
        read(spec["protocol_path"], spec["protocol_sha256"])
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
            need(result["speed_mps"] == cell["speed_mps"] and result["family"] == cell["family"], "Java speed/family differs")
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
        rates = result["population_audit"] if method in (G31, TARAU) else result["metrics"]
        rate_std = rates["success_rate_std"] if method in (G31, TARAU) else rates["success_std_rate"] if method == HCA else rates["success_rate_std"]
        rate_literal = rates["success_rate_paper_literal"] if method in (G31, TARAU) else rates["success_std_minus_2700_rate"] if method == HCA else rates["success_rate_paper_literal"]
        metrics = dict(zip(TIMINGS, timings if full else [None] * 6))
        metrics.update(TH=done, completion_rate=done/n, success_std_rate=rate_std, success_paper_literal_rate=rate_literal)
        row = snapshot_rows[name]
        for key, value in metrics.items():
            same(row[key], value, f"snapshot metric {key}: {name}")
        need(row["full_population_complete"] is full and row["raw_bag_count"] == n and row["segment_count"] == segments, "snapshot population differs")
        need(row["normalized_sha256"] == sha(result_path) and row["runner_status_sha256"] == sha(status_path), "snapshot result/status SHA differs")
        need(row["orchestration_record_sha256"] == sha(child_receipt) and Path(row["orchestration_record_path"]).resolve() == child_receipt.resolve(), "snapshot receipt SHA/path differs")
        for key in ("runner_sha256", "spec_sha256", *GRID_FIELDS):
            need(row[key] == cell[key], f"snapshot identity differs {key}: {name}")
        need(row["workload_identity_sha256"] == spec["workload_identity_sha256"], "snapshot workload identity differs")
        for key in ("raw_sha256", "canonical_sha256", "map_sha256"):
            need(row[key] == identity[key], "snapshot input SHA differs")
        entry = {"cell_id": name, "family": cell["family"], "scenario_index": cell["scenario_index"], **{k: cell[k] for k in COORD}, "receipt_status": receipt["status"],
                 "normalized_sha256": sha(result_path), "runner_status_sha256": sha(status_path),
                 "spec_sha256": cell["spec_sha256"], "workload_identity_sha256": spec["workload_identity_sha256"],
                 "full_population_complete": full, "raw_bags": n, "completed_raw_bags": done,
                 "segment_count": segments, "completed_segment_count": completed_segments,
                 "formal_timing_status": "FULL_POPULATION_FINITE" if full else "ALL_FORMAL_THT_NULL"}
        checked.append(entry)
        groups[tuple(cell[k] for k in GRID_FIELDS if k != "seed")].append(entry)
    finish_review(plan, snapshot, old_snapshot, checked, records, groups, output)



if __name__ == "__main__":
    run()
