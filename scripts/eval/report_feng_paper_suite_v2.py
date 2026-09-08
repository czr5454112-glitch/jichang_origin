"""Read-only snapshots for the explicitly reduced 576-cell Feng paper suite.

No simulator, normalizer, native loader or bootstrap is invoked. Every frozen
coordinate is retained, including missing, failed and censored cells. The small
result envelopes are checked against frozen inputs; this is not a substitute
for the runners' independent native/archive verification.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
G31 = "G31_S4_ADVERTISED_FAULT_REPAIR_V1"
HCA = "HCA_TIME_LABEL_REPAIR_V3"
DH = "FENG_DH_PAPER_SUITE_V6"
TARAU = "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY"
METHODS = (G31, HCA, DH, TARAU)
LABELS = {G31: "G31", HCA: "HCA V3", DH: "CIE-DH V6", TARAU: "Tarau 适配"}
COORD = ("family", "map", "load_factor", "speed_mps", "scenario_index", "seed")
TIMINGS = tuple(f"tht_{clock}_{stat}_seconds" for clock in ("D", "native")
                for stat in ("min", "mean", "max"))
METRICS = ("TH", "completion_rate", "success_std_rate", "success_paper_literal_rate", *TIMINGS)
STATES = ("COMPLETE", "MISSING", "RUNNING", "POSTPROCESSING", "FAILED", "INVALID")
SCHEMA = "czr005.feng_paper_suite.report_snapshot.v2"
BASE_SEEDS = (104729, 130363, 155921, 181081, 205759, 232003, 257053, 283303, 308081, 333667)
FAULT_SEEDS = BASE_SEEDS[:3]
FAULT_SCENARIOS = (1, 2, 9, 14)
FAMILY_COUNTS = {"base": 480, "all_day_fault": 96}
EXPECTED_CELLS = sum(FAMILY_COUNTS.values())
EXPECTED_PAIRS = 408
EXPECTED_METHOD_GROUPS = 80
EXPECTED_PAIRED_GROUPS = 52


def registered_seeds(fam):
    require(fam in FAMILY_COUNTS, "unregistered family")
    return BASE_SEEDS if fam == "base" else FAULT_SEEDS


def expected_coordinates():
    expected = set()
    for m, load, speed, seed, method in itertools.product(
            ("map2", "nanning"), (1, 2), (1.5, 2.5, 3.0), BASE_SEEDS, METHODS):
        expected.add(("base", m, load, speed, 0, seed, method))
    for m, load, scenario, seed, method in itertools.product(
            ("map2", "nanning"), (1, 2), FAULT_SCENARIOS, FAULT_SEEDS, (G31, HCA)):
        expected.add(("all_day_fault", m, load, 2.5, scenario, seed, method))
    return expected


def validate_coordinates(cells):
    actual = [tuple(c[k] for k in (*COORD, "method")) for c in cells]
    require(all(type(c["seed"]) is int and type(c["scenario_index"]) is int for c in cells),
            "seed/scenario must be explicit integers")
    require(len(actual) == len(set(actual)) == EXPECTED_CELLS and set(actual) == expected_coordinates(),
            "registered 480+96 coordinate set differs; arbitrary masks are forbidden")


def validate_scope_contract(scope):
    require(scope.get("schema") == "czr005.feng_paper_suite.reduced_scope.v1", "unknown reduced scope contract")
    require(scope.get("cell_count") == EXPECTED_CELLS and scope.get("family_counts") == FAMILY_COUNTS,
            "scope count differs")
    require(scope.get("execution_order") == ["base", "all_day_fault"], "scope execution order differs")
    for fam in FAMILY_COUNTS:
        s = scope[fam]
        expected = {"maps": ["map2", "nanning"], "load_factors": [1.0, 2.0],
                    "speed_mps": [1.5, 2.5, 3.0] if fam == "base" else [2.5],
                    "seeds": list(registered_seeds(fam)), "methods": list(METHODS if fam == "base" else (G31, HCA))}
        if fam == "all_day_fault":
            expected.update(scenario_indices=list(FAULT_SCENARIOS), initial_line_sets=[[1], [2], [1, 7], [2, 4, 6]])
        require(all(s.get(k) == v for k, v in expected.items()), f"scope {fam} registration differs")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def family(value):
    return "all_day_fault" if value == "fault" else value


class Reader:
    """Cache immutable small inputs; capture each mutable result exactly once."""
    def __init__(self):
        self.cache = {}
        self.files = {}

    def read(self, path, expected=None):
        path = Path(path).resolve(strict=True)
        key = str(path)
        if key not in self.cache:
            data = path.read_bytes()
            value = json.loads(data.decode("utf-8-sig"))
            require(isinstance(value, dict), f"JSON object required: {path}")
            self.cache[key] = value
            self.files[key] = {"path": key, "sha256": digest(data), "bytes": len(data)}
        if expected is not None:
            require(self.files[key]["sha256"] == expected, f"SHA mismatch: {path}")
        return self.cache[key]

    def sha(self, path):
        self.read(path)
        return self.files[str(Path(path).resolve())]["sha256"]


def load_plan(path, reader):
    plan = reader.read(path)
    require(plan.get("schema") == "czr005.feng_paper_suite.plan.v1", "unknown plan schema")
    require(plan.get("status") == "FROZEN_SPECS_NOT_ALL_EXECUTED", "plan is not frozen")
    contract = plan["scope_contract"]
    validate_scope_contract(reader.read(contract["path"], contract["sha256"]))
    cells = [dict(c, family=family(c["family"]),
                  load_factor=c.get("load_factor", c.get("load"))) for c in plan["cells"]]
    require(len(cells) == EXPECTED_CELLS, "the report requires all 576 registered cells")
    require(plan.get("family_counts") == FAMILY_COUNTS and plan.get("cell_count") == EXPECTED_CELLS,
            "plan count declaration differs from registered reduction")
    require(plan.get("execution_order") == ["base", "all_day_fault"], "registered execution order differs")
    require(len({c["cell_id"] for c in cells}) == EXPECTED_CELLS, "duplicate cell ID")
    require(len({str(Path(c["output_dir"]).resolve()) for c in cells}) == EXPECTED_CELLS, "duplicate output")
    seeds = sorted({c["seed"] for c in cells})
    require(tuple(seeds) == BASE_SEEDS, "registered base seed set differs")
    validate_coordinates(cells)
    reduction = plan["scope_reduction"]
    require(reduction.get("user_approved") is True and reduction.get("normal_first") is True,
            "reduction authorization/order provenance missing")
    previous = reader.read(reduction["source_plan_path"], reduction["source_plan_sha256"])
    previous_by_id = {c["cell_id"]: c for c in previous["cells"]}
    require(len(previous["cells"]) == len(previous_by_id) == 1760, "reduction source is not the complete prior plan")
    require(all(previous_by_id.get(c["cell_id"]) == c for c in cells), "retained cell identity changed during reduction")
    removed = set(previous_by_id) - {c["cell_id"] for c in cells}
    require(reduction.get("removed_count") == len(removed) == 1184
            and len(reduction["removed_cell_ids"]) == len(set(reduction["removed_cell_ids"]))
            and set(reduction["removed_cell_ids"]) == removed, "reduction removal inventory differs")
    protocols = {family(p["family"]): p for p in plan["protocols"]}
    require(set(protocols) == {"base", "all_day_fault"}, "both protocols required")
    for p in protocols.values():
        reader.read(p["path"], p["sha256"])
    specs = {}
    for c in cells:
        spec = reader.read(c["spec_path"], c["spec_sha256"])
        for key in ("method", "map", "load_factor", "speed_mps", "seed"):
            require(spec[key] == c[key], f"plan/spec {key}: {c['cell_id']}")
        require(family(spec["family"]) == c["family"], "plan/spec family mismatch")
        require(spec.get("scenario_index", 0) == c["scenario_index"], "scenario mismatch")
        require(spec.get("timing_policy") == "full_population_only", "wrong timing policy")
        require(spec.get("horizon_seconds", spec.get("fixed_horizon_seconds")) == 98259,
                "wrong registered horizon")
        p = protocols[c["family"]]
        require(Path(spec["protocol_path"]).resolve() == Path(p["path"]).resolve()
                and spec["protocol_sha256"] == p["sha256"], "wrong family protocol")
        specs[c["cell_id"]] = spec
    return plan, cells, specs, seeds


def finite(value, label):
    require(type(value) in (int, float) and math.isfinite(value), f"invalid {label}: {value}")
    return value


def integer(value, label):
    finite(value, label)
    require(value == int(value) and value >= 0, f"invalid integer {label}")
    return int(value)


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)


def extract_metrics(method, result):
    """Translate names only. Never recompute a survivor cohort or change a clock."""
    if method in (G31, TARAU):
        a = result["population_audit"]
        require(a["status"] == "PASS" and a["gates"] and all(v is True for v in a["gates"].values()), "CPP audit failed")
        full, n = a["full_population_complete"], a["raw_bag_count"]
        values = {"TH": a["completed_raw_bag_count"], "completion_rate": a["completion_rate"],
                  "success_std_rate": a["success_rate_std"],
                  "success_paper_literal_rate": a["success_rate_paper_literal"]}
        require(a["timing_eligible"] is full, "CPP timing eligibility mismatch")
        for clock, name in (("D", "primary_timing"), ("native", "native_timing")):
            timing = a[name]
            require((timing is not None) is full, "CPP timing/full mismatch")
            if full:
                require(timing["count"] == n, "CPP timing count differs from full population")
            for stat in ("min", "mean", "max"):
                values[f"tht_{clock}_{stat}_seconds"] = timing[stat] if full else None
        extra = {"segment_count": a["segment_count"], "completed_segment_count": a["completed_segment_count"],
                 **a.get("trace", {})}
    else:
        a, m = result.get("population_audit", {}), result["metrics"]
        require((a.get("status") if method == HCA else result.get("audit_status")) == "PASS", "Java audit failed")
        require(result.get("survivor_timing_used") is False, "survivor timing is forbidden")
        full = result["full_population_complete"]
        if method == HCA:
            require(a.get("full_population_complete") is full, "HCA audit completion flag differs")
        n = result["raw_bag_denominator"] if method == HCA else m["raw_bag_denominator"]
        values = {"TH": m["completed_raw_bag_count"], "completion_rate": m.get("completion_rate"),
                  "success_std_rate": m["success_std_rate" if method == HCA else "success_rate_std"],
                  "success_paper_literal_rate": m["success_std_minus_2700_rate" if method == HCA else "success_rate_paper_literal"]}
        # Historical HCA business helper supplies counts; completion rate has a
        # single fixed-denominator definition and may not have a named field.
        if values["completion_rate"] is None:
            values["completion_rate"] = values["TH"] / n
        prefixes = (("D", "tht_scheduled_release"), ("native", "tht_admission")) if method == HCA else (
            ("D", "tht_D"), ("native", "tht_native"))
        for clock, prefix in prefixes:
            for stat in ("min", "mean", "max"):
                values[f"tht_{clock}_{stat}_seconds"] = m[f"{prefix}_{stat}_seconds"]
        extra = {"segment_count": result.get("segment_denominator"),
                 "completed_segment_count": a.get("completed_segment_count", m.get("completed_segment_count"))}
    require(type(full) is bool, "completion flag must be a boolean")
    n, done = integer(n, "raw population"), integer(values["TH"], "TH")
    require(n > 0 and done <= n and full == (done == n), "population completion mismatch")
    for key in ("completion_rate", "success_std_rate", "success_paper_literal_rate"):
        value = finite(values[key], key)
        require(0 <= value <= 1, f"rate outside [0,1]: {key}")
    require(close(values["completion_rate"], done/n), "completion rate denominator mismatch")
    require(values["success_paper_literal_rate"] <= values["success_std_rate"] + 1e-9
            <= values["completion_rate"] + 2e-9, "deadline/completion nesting fails")
    for key in TIMINGS:
        require((values[key] is not None) is full, "formal THT must be NA exactly for incomplete population")
        if full:
            finite(values[key], key)
    if full:
        for clock in ("D", "native"):
            lo, avg, hi = (values[f"tht_{clock}_{s}_seconds"] for s in ("min", "mean", "max"))
            require(lo <= avg + 1e-8 and avg <= hi + 1e-8, "THT statistic order fails")
    return {"raw_bag_count": n, "full_population_complete": full,
            "unfinished_raw_bag_count": n-done, **values, **extra}


def orchestration_records(plan, cells, reader):
    """Only matching cell/spec/runner records can refine stale native status."""
    result_root = Path(plan["result_root"])
    campaign = result_root.parent if result_root.name == "cells" else result_root
    by_id = {c["cell_id"]: c for c in cells}
    records = {}
    for path in sorted((campaign / "orchestration").glob("*/cells/*/status.json")):
        c = by_id.get(path.parent.name)
        if c is None:
            continue
        record = reader.read(path)
        if any(record.get(k) != c[k] for k in ("cell_id", "method", "spec_sha256", "runner_sha256")):
            continue  # An earlier superseded plan is not this execution identity.
        if Path(record.get("output_dir", "")).resolve() != Path(c["output_dir"]).resolve():
            continue
        stamp = finite(record.get("started_at_unix"), "orchestration start")
        old = records.get(c["cell_id"])
        if old is None or (stamp, str(path)) > (old["started_at_unix"], old["_path"]):
            records[c["cell_id"]] = dict(record, _path=str(path), _sha256=reader.sha(path))
    return records


def apply_orchestration(row, record):
    if record is None:
        return row
    row.update(orchestration_status=record["status"], orchestration_record_path=record["_path"],
               orchestration_record_sha256=record["_sha256"], orchestration_wall_seconds=record.get("wall_seconds"))
    state = record["status"]
    if state in ("FAILED", "TIMED_OUT", "ABORTED", "TIMEOUT_TERMINATION_FAILED", "ABORT_TERMINATION_FAILED"):
        row.update(cell_state="FAILED", terminal_result_accepted=False, error=record.get("error", state))
    elif state in ("CHECKING", "RUNNING") and row["cell_state"] not in ("FAILED", "INVALID"):
        row.update(cell_state="POSTPROCESSING" if row.get("normalized_sha256") else "RUNNING",
                   terminal_result_accepted=False)
    elif state in ("COMPLETE", "REUSED_VERIFIED") and row["cell_state"] == "COMPLETE":
        if record.get("normalized_result_sha256") != row["normalized_sha256"]:
            row.update(cell_state="INVALID", terminal_result_accepted=False,
                       error="orchestration/result SHA mismatch")
    if row["cell_state"] in ("FAILED", "INVALID"):
        for k in METRICS:
            row[k] = None
    return row


def observe_cell(cell, spec, reader):
    row = {k: cell[k] for k in ("cell_id", *COORD, "method", "output_dir", "spec_sha256", "runner_sha256")}
    row.update(cell_state="MISSING", runner_status=None, normalized_status=None,
               error=None, full_population_complete=None, terminal_result_accepted=False,
               postprocessing_pending=False, **{k: None for k in METRICS})
    output = Path(cell["output_dir"])
    result_path, status_path = output / "normalized_result.json", output / "runner_status.json"
    row.update(normalized_path=str(result_path), runner_status_path=str(status_path))
    try:
        identity = reader.read(spec["workload_identity_path"], spec["workload_identity_sha256"])
        for k in ("map", "load_factor", "seed"):
            require(identity[k] == cell[k], f"workload {k} differs")
        failed = sorted(tuple(e) for e in spec.get("failed_edges", []))
        require(len(set(failed)) == len(failed), "duplicate failed edges")
        if cell["family"] == "all_day_fault":
            require(failed and failed == sorted(tuple(e) for e in spec["affected_edges"]), "closure/failed set differs")
        else:
            require(not failed, "fault edges in base cell")
        signature = {k: identity[k] for k in ("raw_sha256", "canonical_sha256", "map_sha256", "raw_bag_count", "segment_count")}
        signature.update(horizon_seconds=98259, failed_edges=failed,
                         initial_failed_edges=sorted(tuple(e) for e in spec.get("initial_failed_edges", [])),
                         fault_mapping_sha256=spec.get("fault_mapping_sha256"))
        row.update(workload_identity_sha256=spec["workload_identity_sha256"],
                   raw_sha256=identity["raw_sha256"], canonical_sha256=identity["canonical_sha256"],
                   map_sha256=identity["map_sha256"], input_signature_sha256=digest(json_bytes(signature)),
                   raw_bag_count=identity["raw_bag_count"], segment_count=identity["segment_count"],
                   horizon_seconds=98259, initial_failed_edge_count=len(spec.get("initial_failed_edges", [])),
                   affected_edge_count=len(failed), affected_edges_json=json.dumps(failed),
                   fault_mapping_sha256=spec.get("fault_mapping_sha256"))
        status = reader.read(status_path) if status_path.exists() else {}
        row["runner_status"] = status.get("status")
        row["runner_status_sha256"] = reader.sha(status_path) if status else None
        state = str(status.get("status", "")).upper()
        row["postprocessing_pending"] = any((output / name).exists() for name in ("run.lock", "execution.lock", ".run_lock"))
        if state.startswith("FAIL") or (output / "run_failure.json").exists():
            row.update(cell_state="FAILED", error=status.get("error", "runner failure; see native output"))
            return row
        if not result_path.exists():
            row["cell_state"] = ("POSTPROCESSING" if state in ("COMPLETE", "NATIVE_COMPLETE") else
                                 "RUNNING" if state or row["postprocessing_pending"] else "MISSING")
            return row
        result = reader.read(result_path)
        row.update(normalized_status=result.get("status"), normalized_sha256=reader.sha(result_path))
        if state != "COMPLETE":
            row["cell_state"] = "POSTPROCESSING"
            return row
        require(result.get("status") == "COMPLETE", "normalized result not complete")
        for k in ("method", "map", "load_factor", "seed"):
            require(result[k] == cell[k], f"normalized {k} differs")
        require(result["workload_identity_sha256"] == spec["workload_identity_sha256"], "normalized workload identity differs")
        method = cell["method"]
        if method in (G31, TARAU):
            require(status["normalized_result_sha256"] == row["normalized_sha256"], "normalized result SHA differs")
            rs, p = result["spec"], result["provenance"]
            for key, value in spec.items():
                # prepare_spec adds scenario.family to an existing scenario.
                if key == "scenario":
                    require(all(rs[key].get(k) == v for k, v in value.items()), "resolved scenario differs")
                else:
                    require(rs.get(key) == value, f"resolved spec {key} differs")
            for k in ("runner_sha256", "protocol_sha256", "workload_identity_sha256", "binary_sha256"):
                require(p[k] == (cell[k] if k == "runner_sha256" else spec[k]), f"CPP {k} differs")
            for k in ("raw_sha256", "canonical_sha256", "map_sha256"):
                require(p[k] == identity[k], f"CPP {k} differs")
            row["binary_sha256"] = p["binary_sha256"]
        else:
            require(result["speed_mps"] == cell["speed_mps"] and family(result["family"]) == cell["family"], "normalized speed/family differs")
            sk = "run_spec_sha256" if method == HCA else "spec_sha256"
            rk = "python_runner_sha256" if method == HCA else "runner_sha256"
            require(result[sk] == cell["spec_sha256"] == status[sk], "Java spec SHA differs")
            require(status[rk] == cell["runner_sha256"], "Java runner SHA differs")
            require(status["protocol_sha256"] == spec["protocol_sha256"] and status["returncode"] == 0, "Java terminal/protocol differs")
            if method == HCA:
                require(status["build_identity_sha256"] == spec["build_identity_sha256"], "HCA build differs")
                for k in ("raw", "canonical", "map"):
                    require(result[f"workload_{k}_sha256"] == identity[f"{k}_sha256"] == status["inputs"][k]["sha256"], "HCA input differs")
                row.update(source_sha256=status["source_sha256"], class_sha256=status["class_sha256"])
            else:
                build_path = output / "build_identity.json"
                reader.read(build_path, spec["build_identity_sha256"])
        values = extract_metrics(method, result)
        require(values["raw_bag_count"] == identity["raw_bag_count"], "raw denominator differs")
        if values.get("segment_count") is not None:
            require(values["segment_count"] == identity["segment_count"], "segment denominator differs")
        else:
            values["segment_count"] = identity["segment_count"]
        completed_segments = integer(values["completed_segment_count"], "completed segments")
        require(completed_segments <= identity["segment_count"], "too many completed segments")
        require(values["full_population_complete"] == (completed_segments == identity["segment_count"]),
                "segment/raw completion disagree")
        row.update(values)
        row["native_wall_seconds"] = result.get("native_wall_seconds", result.get("wall_seconds", status.get("wall_seconds")))
        if row["native_wall_seconds"] is not None:
            require(finite(row["native_wall_seconds"], "wall time") >= 0, "negative wall time")
        row.update(cell_state="POSTPROCESSING" if row["postprocessing_pending"] else "COMPLETE",
                   terminal_result_accepted=not row["postprocessing_pending"])
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
        row.update(cell_state="INVALID", error=f"{type(error).__name__}: {error}", terminal_result_accepted=False)
        for k in METRICS:
            row[k] = None
    return row


def pair_cells(rows):
    validate_coordinates(rows)
    by_coord = defaultdict(dict)
    for row in rows:
        by_coord[tuple(row[k] for k in COORD)][row["method"]] = row
    pairs = []
    for coordinate, methods in sorted(by_coord.items()):
        g = methods[G31]
        for baseline in (HCA, DH, TARAU):
            if baseline not in methods:
                continue
            b = methods[baseline]
            pair = dict(zip(COORD, coordinate))
            pair.update(reference=G31, baseline=baseline, g31_cell_id=g["cell_id"], baseline_cell_id=b["cell_id"],
                        g31_state=g["cell_state"], baseline_state=b["cell_state"],
                        pair_status="INCOMPLETE", tht_pair_eligible=False)
            for name in METRICS:
                pair.update({f"g31_{name}": None, f"baseline_{name}": None,
                             f"g31_benefit_{name}": None, f"g31_benefit_{name}_percent": None})
            if g["cell_state"] == b["cell_state"] == "COMPLETE":
                same = g.get("input_signature_sha256") == b.get("input_signature_sha256") and g.get("input_signature_sha256") is not None
                pair["pair_status"] = "COMPLETE" if same else "INPUT_MISMATCH"
                if same:
                    pair["tht_pair_eligible"] = g["full_population_complete"] and b["full_population_complete"]
                    for name in METRICS:
                        if name in TIMINGS and not pair["tht_pair_eligible"]:
                            continue
                        gv, bv = g[name], b[name]
                        benefit = bv-gv if name in TIMINGS else gv-bv
                        pair[f"g31_{name}"] = gv
                        pair[f"baseline_{name}"] = bv
                        pair[f"g31_benefit_{name}"] = benefit
                        pair[f"g31_benefit_{name}_percent"] = benefit / bv * 100 if bv != 0 else None
                    for name in ("completion_rate", "success_std_rate", "success_paper_literal_rate"):
                        pair[f"g31_benefit_{name}_pp"] = pair[f"g31_benefit_{name}"] * 100
            pairs.append(pair)
    require(len(pairs) == EXPECTED_PAIRS, "all 408 registered G31/baseline seed pairs required")
    return pairs


def mean(values):
    return statistics.fmean(values) if values else None


def group_results(rows, pairs, seeds):
    require(tuple(seeds) == BASE_SEEDS, "registered base seed set differs")
    validate_coordinates(rows)
    expected_pair_coordinates = {coordinate for coordinate in expected_coordinates() if coordinate[-1] != G31}
    actual_pair_coordinates = [tuple(p[k] for k in (*COORD, "baseline")) for p in pairs]
    require(len(actual_pair_coordinates) == len(set(actual_pair_coordinates)) == EXPECTED_PAIRS
            and set(actual_pair_coordinates) == expected_pair_coordinates,
            "registered paired coordinates differ")
    method_groups, paired_groups = [], []
    for population, keys, target in ((rows, (*COORD[:-1], "method"), method_groups),
                                     (pairs, (*COORD[:-1], "baseline"), paired_groups)):
        groups = defaultdict(list)
        for row in population:
            groups[tuple(row[k] for k in keys)].append(row)
        for key, group in sorted(groups.items(), key=lambda kv: (kv[0][0] != "base", *kv[0][1:-1], METHODS.index(kv[0][-1]))):
            required = registered_seeds(key[0])
            nseeds = len(required)
            require(tuple(sorted(r["seed"] for r in group)) == required, "group does not contain its registered seeds")
            paired = population is pairs
            accepted = [r for r in group if r["pair_status" if paired else "cell_state"] == "COMPLETE"]
            full = [r for r in accepted if r["tht_pair_eligible" if paired else "full_population_complete"]]
            item = dict(zip(keys, key))
            item.update(expected_seed_count=nseeds, registered_seeds=list(required), complete_seed_count=len(accepted),
                        tht_eligible_seed_count=len(full),
                        status=f"COMPLETE_{nseeds}_SEEDS" if len(accepted) == nseeds else f"INCOMPLETE_{nseeds}_SEEDS",
                        tht_status=f"FULL_POPULATION_{nseeds}_SEEDS" if len(full) == nseeds else "NA_NOT_ALL_REGISTERED_SEEDS_FULL")
            if not paired:
                for name in (*METRICS, "native_wall_seconds"):
                    values = [r.get(name) for r in accepted]
                    item[name] = mean(values) if len(accepted) == nseeds and all(v is not None for v in values) else None
                item["affected_edge_count"] = group[0].get("affected_edge_count")
            else:
                item["metrics"] = {}
                for name in METRICS:
                    eligible = len(accepted) == nseeds and (name not in TIMINGS or len(full) == nseeds)
                    stat = {"eligible": eligible, "g31_mean": None, "baseline_mean": None,
                            "mean_benefit": None, "benefit_percent_of_means": None,
                            "mean_seed_benefit_percent": None, "benefit_pp": None,
                            "wins": None, "ties": None, "losses": None}
                    if eligible:
                        gv = mean([r[f"g31_{name}"] for r in accepted])
                        bv = mean([r[f"baseline_{name}"] for r in accepted])
                        benefits = [r[f"g31_benefit_{name}"] for r in accepted]
                        percentages = [r[f"g31_benefit_{name}_percent"] for r in accepted]
                        stat.update(g31_mean=gv, baseline_mean=bv, mean_benefit=mean(benefits),
                                    benefit_percent_of_means=mean(benefits)/bv*100 if bv != 0 else None,
                                    mean_seed_benefit_percent=mean(percentages) if all(v is not None for v in percentages) else None,
                                    benefit_pp=mean(benefits)*100 if name.endswith("_rate") else None,
                                    wins=sum(v > 1e-9 for v in benefits), ties=sum(abs(v) <= 1e-9 for v in benefits),
                                    losses=sum(v < -1e-9 for v in benefits))
                    item["metrics"][name] = stat
            target.append(item)
    require(len(method_groups) == EXPECTED_METHOD_GROUPS and len(paired_groups) == EXPECTED_PAIRED_GROUPS,
            "registered group count differs")
    return method_groups, paired_groups


def fmt(value, places=3):
    return "NA" if value is None else f"{value:.{places}f}"


def wtl(metric):
    return "NA" if not metric["eligible"] else f"{metric['wins']}/{metric['ties']}/{metric['losses']}"


def summarize_progress(rows, pairs):
    validate_coordinates(rows)
    family_progress = {}
    for fam, expected in FAMILY_COUNTS.items():
        selected = [r for r in rows if r["family"] == fam]
        counts = Counter(r["cell_state"] for r in selected)
        require(len(selected) == expected and set(counts) <= set(STATES), "family state coverage differs")
        accepted = [r for r in selected if r["cell_state"] == "COMPLETE"]
        mismatch = sum(p["pair_status"] == "INPUT_MISMATCH" for p in pairs if p["family"] == fam)
        family_progress[fam] = {"expected_cells": expected, "accepted_cells": len(accepted),
            "cell_state_counts": {s: counts[s] for s in STATES},
            "full_population_cells": sum(r["full_population_complete"] for r in accepted),
            "incomplete_population_cells": sum(not r["full_population_complete"] for r in accepted),
            "status": "COMPLETE" if len(accepted) == expected and not mismatch else "PARTIAL"}
    return {"status": "COMPLETE" if all(v["status"] == "COMPLETE" for v in family_progress.values())
            else "PARTIAL_NOT_A_FINAL_CONCLUSION", "family_progress": family_progress}


def render_report(snapshot):
    counts = snapshot["cell_state_counts"]
    fp = snapshot["family_progress"]
    lines = ["# Feng 论文实验套件：缩减范围的状态与结果快照", "",
             f"生成于 {snapshot['observed_finished_at_utc']}；状态 **{snapshot['status']}**。",
             "",
             "范围：基础实验 480 格＝两地图 × 1×/2× × 1.5/2.5/3 m/s × 十个共同种子 × 四方法；"
             "全天断线实验 96 格＝两地图 × 1×/2× × 指定四情景 [1,2,9,14] × 指定三种子 "
             "[104729,130363,155921] × G31/HCA，速度仅 2.5 m/s。"
             "动态/静态速度偏差已取消；CIE-DH、Tarau 不在此次故障矩阵。",
             "",
             "这是开跑后经用户确认的范围缩减，原完整计划及已有输出保留。缩减故障子集不等于完整 16 场景论文复现，"
             "也不能由这三种子推广为十种子结论。主故障仍为首次规划前已知的全天故障，无重连；"
             "运营中通知/恢复的既有微例仅提供有界机制证据，不计入此主故障矩阵。"
             "后续顺序为先完成基础 480 格，再完成故障 96 格；此前已取得的故障证据按原身份保留。",
             "原单格协议继续保留物理参数及完整情景登记；其旧版 1280 故障格计数是原登记范围，"
             "当前采样范围由 SHA 绑定的缩减 scope contract 决定，严格为 96 格。",
             "",
             f"基础：{fp['base']['accepted_cells']}/{fp['base']['expected_cells']}，{fp['base']['status']}；"
             f"故障子集：{fp['all_day_fault']['accepted_cells']}/{fp['all_day_fault']['expected_cells']}，{fp['all_day_fault']['status']}。"
             "只有全部 576 个注册格有效终止且配对输入一致，整个缩减任务才标 COMPLETE；基础单独完成不表示全任务完成。",
             "",
             f"全部 {snapshot['expected_cells']} 格均列入 [cells.csv](cells.csv)：终态且后处理结束 {counts['COMPLETE']}；"
             f"缺失 {counts['MISSING']}；运行中 {counts['RUNNING']}；后处理/清理中 {counts['POSTPROCESSING']}；"
             f"失败 {counts['FAILED']}；证据字段不一致 {counts['INVALID']}。"
             f"已接受终态中，人口全完 {snapshot['full_population_cell_count']}，人口未全完 {snapshot['censored_population_cell_count']}。",
             "",
             "**部分进度不能当作完整缩减矩阵结论。** 基础组必须齐备指定十种子、故障组必须齐备指定三种子才显示组平均；"
             "THT 比较还要求双方该组的全部注册种子均全人口完成。不会临时删除不利种子、使用幸存者队列，或将 2× 一律置 NA。"
             "有任一缺格/失败/证据不一致时，不宣称完整缩减矩阵优势。即使全部完成，也须逐指标判断，保留负收益、持平与劣势。",
             "",
             "主口径 THT(D)＝每个原始袋所有规范段的 Σ(E−canonical scheduled D)。这是双方共同计划释放时钟的操作定义；"
             "Feng 原文同名 THT 的入网事件与此起点尚未证明完全相同，不能称论文 exact-THT 复现。"
             "另一计时口径 THT(native) 用原生 admitted/first-admission，HCA 用成功 planning 后 processed 时间；"
             "这些事件也不完全等义，因此两口径均可见，不能据单列认定同一物理 THT 全面优劣。"
             "EBS 两段保持共同输入中的独立计划任务，未另加前后依赖。",
             "",
             "TH＝固定 98259 s 时域内全段完成的原始袋数；完成率及两种成功率均除以全部原始袋数。"
             "STD 成功率使用原始业务 STD；论文文字截止另列 STD−2700 s。后者与现有 EBS 出库计划存在已披露矛盾，"
             "不能把两种截止混称准时率。故障影响线路数来自共同输入的 closure，是情景属性，不能算方法传播或性能优势。",
             "",
             "此处的终态接受只复核小型结果、状态、冻结 spec/输入身份和指标资格。"
             "本脚本不启动模拟、不重算原生轨迹，也不替代独立档案校验或连续几何安全证明。"
             "CIE-DH V6 为已披露假设的 V5 适配；Tarau 为路由适配而非原始完整控制器。"
             "G31 故障修复使用已通知拓扑的全图势重建；基础正常路径保持原势。"
             "两图拓扑、物理执行器和作者修订稿/正式出版全文的证据边界仍然保留。",
             "",
             "C++ 的 active-state 执行核验与 bounded lifecycle 日志完整性分列。日志截断时不宣称 full trace。"
             "墙钟是各原生运行记录，受并发、宿主负载、实现语言及归档边界影响，不作纯路由算法复杂度排名。",
             "“运行中”指所存运行记录，并非此刻进程存活证明；若匹配执行身份的外层记录明确超时、中止或验证失败，"
             "该格列为失败，即使原生状态仍停留在 RUNNING/COMPLETE。外层记录和原生状态均在逐格 CSV 保留。",
             "",
             "统计粒度：先计算每种子的袋级 min/mean/max，再对该科目预定的全部种子（基础十个、故障三个）取对应统计量的算术平均；"
             "下表的 min/max 因而是“种子级 min/max 的平均”，并非把多种子所有袋合并后的极值。"
             "配对收益百分比＝(baseline 组均值−G31 组均值)/baseline 组均值（THT），TH 则方向相反；"
             "分母为零时百分比 NA，绝对差仍保留。成功率差单位为百分点。未计算置信区间。",
             "",
             "## 每组注册种子的同口径观测", "",
             "尚未齐备该组全部注册种子时只列状态；N 为基础 10、故障 3。全部逐格观测保留在 CSV。D/native 同行显示；NA 不代表零。", "",
             "|科目|地图/负荷/速度/情景|方法|终态/N；全完/N|TH|完成率 %|STD %|STD−2700 %|THT(D) min/mean/max s|THT(native) min/mean/max s|记录墙钟 s|",
             "|---|---|---|---|---:|---:|---:|---:|---|---|---:|"]
    for g in snapshot["method_groups"]:
        desc = f"{g['map']}/{g['load_factor']:g}×/{g['speed_mps']:g}/q{g['scenario_index']:02d}"
        timing = [" / ".join(fmt(g[f"tht_{clock}_{s}_seconds"]) for s in ("min", "mean", "max")) for clock in ("D", "native")]
        rates = [fmt(g[k]*100 if g[k] is not None else None) for k in ("completion_rate", "success_std_rate", "success_paper_literal_rate")]
        lines.append(f"|{'基础' if g['family']=='base' else '全天故障'}|{desc}|{LABELS[g['method']]}|"
                     f"{g['complete_seed_count']}/{g['expected_seed_count']}；{g['tht_eligible_seed_count']}/{g['expected_seed_count']}|{fmt(g['TH'])}|"
                     + "|".join(rates + timing + [fmt(g["native_wall_seconds"])]) + "|")
    lines += ["", "## G31 对各 baseline 的配对结果", "",
              "正值表示 G31 在该指标较好，负值表示较差；胜/平/负按该组全部注册种子的逐种子绝对差计算。"
              "主表并列 D 与 native 的均值和最大值收益；最小值收益、双方实数、全部资格和逐种子差值均在 "
              "[paired.csv](paired.csv) 与 [snapshot.json](snapshot.json) 中保留。最小值并非自动全面领先。", "",
              "|科目/地图/负荷/速度/q|baseline|有效/N；THT/N|TH 差（胜/平/负）|TH 收益 %|完成率差 pp|STD 差 pp|STD−2700 差 pp|D mean/max 收益 %|native mean/max 收益 %|D mean 胜/平/负|native mean 胜/平/负|",
              "|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|"]
    for g in snapshot["paired_groups"]:
        m = g["metrics"]
        desc = f"{'基础' if g['family']=='base' else '故障'}/{g['map']}/{g['load_factor']:g}×/{g['speed_mps']:g}/{g['scenario_index']:02d}"
        clocks = [" / ".join(fmt(m[f"tht_{clock}_{s}_seconds"]["benefit_percent_of_means"]) for s in ("mean", "max")) for clock in ("D", "native")]
        lines.append(f"|{desc}|{LABELS[g['baseline']]}|{g['complete_seed_count']}/{g['expected_seed_count']}；{g['tht_eligible_seed_count']}/{g['expected_seed_count']}|"
                     f"{fmt(m['TH']['mean_benefit'])}（{wtl(m['TH'])}）|{fmt(m['TH']['benefit_percent_of_means'])}|"
                     + "|".join([fmt(m[k]["benefit_pp"]) for k in ("completion_rate", "success_std_rate", "success_paper_literal_rate")]
                                + clocks + [wtl(m["tht_D_mean_seconds"]), wtl(m["tht_native_mean_seconds"])]) + "|")
    lines += ["", "## 证据与重生成", "",
              f"计划 SHA256：`{snapshot['plan_sha256']}`；生成器 SHA256：`{snapshot['generator_sha256']}`。",
              f"全部 {snapshot['expected_cells']} 格、{snapshot['expected_pairs']} 个逐种子 G31/baseline 配对、"
              f"{len(snapshot['method_groups'])} 个方法组与 {len(snapshot['paired_groups'])} 个配对组均保留。"
              "快照逐文件读取，开始/结束时间见 JSON；正在运行的格可能在扫描后改变，因此这是进度观察窗口而非全局原子快照。",
              "",
              "```powershell", f'python scripts/eval/report_feng_paper_suite_v2.py --plan "{snapshot["plan_path"]}" --output "新的不存在目录"',
              "```", "",
              "只写新的报告目录，不覆盖先前快照，也不改变 native、normalized、runner、协议或冻结 plan。"
              "JSON 中记录已读取的小型证据文件 SHA，读者可据此复查此时点的具体输入；原生归档是否完整须另行核验。", ""]
    return "\n".join(lines)


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: "NA" if v is None else v for k, v in row.items()} for row in rows)


def generate(plan_path, output):
    output = Path(output).absolute()
    require(not output.exists(), "output directory already exists; snapshots must never be overwritten")
    started = datetime.now(timezone.utc).isoformat()
    reader = Reader()
    plan, cells, specs, seeds = load_plan(plan_path, reader)
    records = orchestration_records(plan, cells, reader)
    rows = [apply_orchestration(observe_cell(c, specs[c["cell_id"]], reader), records.get(c["cell_id"])) for c in cells]
    pairs = pair_cells(rows)
    method_groups, paired_groups = group_results(rows, pairs, seeds)
    counter = Counter(r["cell_state"] for r in rows)
    counts = {s: counter[s] for s in STATES}
    accepted = [r for r in rows if r["cell_state"] == "COMPLETE"]
    pair_mismatch = sum(p["pair_status"] == "INPUT_MISMATCH" for p in pairs)
    snapshot = {"schema": SCHEMA, **summarize_progress(rows, pairs),
                "observed_started_at_utc": started, "observed_finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "plan_path": str(Path(plan_path).resolve()), "plan_sha256": reader.sha(plan_path),
                "generator_path": str(Path(__file__).resolve()), "generator_sha256": digest(Path(__file__).read_bytes()),
                "expected_cells": EXPECTED_CELLS, "observed_cell_rows": len(rows), "family_counts": FAMILY_COUNTS,
                "expected_pairs": EXPECTED_PAIRS, "observed_pair_rows": len(pairs),
                "registered_seeds": seeds, "registered_seeds_by_family": {fam: list(registered_seeds(fam)) for fam in FAMILY_COUNTS},
                "registered_fault_scenarios": list(FAULT_SCENARIOS), "execution_order": ["base", "all_day_fault"],
                "scope_contract": plan["scope_contract"],
                "scope_source_plan": {"path": plan["scope_reduction"]["source_plan_path"],
                                      "sha256": plan["scope_reduction"]["source_plan_sha256"]},
                "scope": "USER_AUTHORIZED_POST_START_REDUCTION_BASE480_FAULT96_NOT_FULL_16_FAULT_REPRODUCTION",
                "cell_state_counts": counts, "pair_input_mismatch_count": pair_mismatch,
                "full_population_cell_count": sum(r["full_population_complete"] for r in accepted),
                "censored_population_cell_count": sum(not r["full_population_complete"] for r in accepted),
                "native_simulations_invoked": 0, "native_archives_reverified": False,
                "validation_scope": "frozen_plan_and_small_result_envelopes_not_native_recomputation_or_physical_proof",
                "cells": rows, "method_groups": method_groups, "paired_groups": paired_groups,
                "source_files": sorted(reader.files.values(), key=lambda x: x["path"])}
    report = render_report(snapshot)
    # Finish all validation before creating the exclusively owned destination.
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / "cells.csv", rows)
    write_csv(output / "paired.csv", pairs)
    (output / "report.md").write_text(report, encoding="utf-8", newline="\n")
    snapshot["output_files"] = [{"path": p.name, "sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                                for p in (output / "cells.csv", output / "paired.csv", output / "report.md")]
    (output / "snapshot.json").write_bytes(json_bytes(snapshot))
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new, nonexistent timestamp snapshot directory")
    args = parser.parse_args()
    snapshot = generate(args.plan, args.output)
    print(json.dumps({k: snapshot[k] for k in ("status", "expected_cells", "cell_state_counts", "full_population_cell_count", "censored_population_cell_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
