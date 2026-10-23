"""Nanning 1x mature-G31/Feng experiments; no edge capacity or body simulator."""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.experiments.g31_feng_alignment import metrics
from scripts.eval import run_g4irsf31_nanning_native as native31
from czr005 import cpp_backend

CAMPAIGN = ROOT / "outputs/experiments/g31_feng_alignment_20261023"
PREVIOUS = ROOT / "outputs/experiments/g31_physical_waiting_20261023"
CANONICAL = ROOT / "artifacts/tasks/g4irsf31_nanning/nanning_1x_canonical.jsonl"
NATIVE_CONTRACT = "mature_G31_S4_J2_R3_no_edge_capacity_independent_segment_schedule"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str)+"\n", encoding="utf-8")


def jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")


def normalize(value):
    return json.loads(json.dumps(value, default=str))


def evidence(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def finish(directory, canonical, segments, manifest, runtime_summary=None, *, horizon=98259.0):
    summary, business = metrics.audit(canonical, segments, horizon=horizon)
    actual = {r["segment_id"]: r for r in segments}
    jsonl(directory / "segments.jsonl", [{**r, **actual[r["segment_id"]]} for r in canonical])
    jsonl(directory / "business.jsonl", business)
    write(directory / "manifest.json", manifest)
    write(directory / "summary.json", {"metrics": summary, "native_summary": runtime_summary})
    print(json.dumps({"arm": manifest["arm"], "segments": summary["completed_transport_legs"],
                      "business": summary["completed_business_bags"],
                      "segment_elapsed": summary["full_population_segment_elapsed_from_canonical_pass_seconds"],
                      "ebs_diagnostic": summary["ebs_causality_violation_count"]}))


def reuse_baselines():
    canonical = metrics.read_jsonl(CANONICAL)
    source = PREVIOUS / "java_native_1x"
    source_manifest = read(source / "source_input_manifest.json")
    # Verify original Java implementation and every runtime map/workload/helper
    # input recorded previously. The original inputdata.txt is lineage only;
    # the command used the projected Nanning raw input instead.
    source_checks = []
    for record in source_manifest["source_comparison"]:
        path = Path(source_manifest["original_project"]) / record["path"]
        source_checks.append({**evidence(path), "expected_sha256": record["original_sha256"]})
        if sha(path) != record["original_sha256"]:
            raise ValueError(f"original Java source changed: {path}")
    input_checks = []
    for record in source_manifest["inputs"]:
        path = Path(record["path"])
        if path.name == "inputdata.txt":
            continue
        input_checks.append({**evidence(path), "expected_sha256": record["sha256"]})
        if sha(path) != record["sha256"]:
            raise ValueError(f"baseline input changed: {path}")
    status = read(source / "run_01/run_status.json")
    if status["status"] != "complete" or status["speed_mps"] != 2 or status["fault_schedule"] != "none":
        raise ValueError("Java baseline run contract mismatch")
    out = CAMPAIGN / "java_original_reused"
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "g31.feng_alignment.arm.v1", "arm": "Java_HCA_original", "reused": True,
                "execution_contract": "original_Feng_Java_node_time_windows_no_edge_capacity",
                "release_contract": "original_Java_source_generation_and_full_route_planning",
                "canonical": evidence(CANONICAL), "original_project": source_manifest["original_project"],
                "verified_original_sources": source_checks, "verified_runtime_inputs": input_checks,
                "source_evidence": [evidence(source / p) for p in ["source_input_manifest.json", "run_01/run_status.json", "run_01/segment_lifecycle.csv", "run_01/routes.csv", "run_01/output.txt", "run_01/outputstarttime.txt"]],
                "wall_seconds_original_run": status["wall_seconds"], "new_execution_performed": False,
                "causality_policy": "independent scheduled EBS segments; violations reported, no unilateral correction"}
    finish(out, canonical, metrics.java_segments(source / "run_01/segment_lifecycle.csv"), manifest)

    source = PREVIOUS / "legacy_g31_1x_reaudit"
    receipt = read(source / "capture_receipt.json")
    binary = Path(receipt["binary"])
    if sha(binary) != receipt["binary_sha256"]:
        raise ValueError("historical G31 binary changed")
    with gzip.open(source / "request.json.gz", "rt", encoding="utf-8") as handle:
        recorded = json.load(handle)
    workload = native31.load_workload(1, native31.DEFAULT_TASK_DIR)
    request, rows, rejected, local = native31.prepare_native_request(native31.case_by_id("t5_2_nanning_1x_speed_2"), workload,
        map_profile_path=native31.DEFAULT_MAP_PROFILE, fault_protocol_path=native31.DEFAULT_FAULT_PROTOCOL, binary=binary)
    if normalize(request) != recorded or rejected:
        raise ValueError("historical G31 request no longer equals the official same-input baseline")
    with gzip.open(source / "native_payload.json.gz", "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    out = CAMPAIGN / "g31_original_reused"
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "g31.feng_alignment.arm.v1", "arm": "G31_original", "reused": True,
                "execution_contract": NATIVE_CONTRACT, "release_contract": "canonical_pass_time_own_source",
                "canonical": evidence(CANONICAL), "binary": evidence(binary),
                "source_evidence": [evidence(source / p) for p in ["request.json.gz", "native_payload.json.gz", "capture_receipt.json", "case.json"]],
                "official_request_exact_match": True, "new_execution_performed": False,
                "wall_seconds_original_native_call": receipt["native_call_wall_seconds_excluding_output_serialization"],
                "causality_policy": "independent scheduled EBS segments; violations reported, no unilateral correction"}
    finish(out, canonical, metrics.native_segments(payload), manifest, payload["summary"])


def run_native(args):
    directory = args.output.resolve()
    if directory.exists():
        raise FileExistsError("preserve existing runs; select a fresh directory")
    canonical = metrics.read_jsonl(CANONICAL)
    workload = native31.load_workload(1, native31.DEFAULT_TASK_DIR)
    release_contract, release_evidence = "canonical_pass_time_own_source", None
    if args.same_hca_release:
        java_rows = metrics.java_segments(args.same_hca_release)
        releases = metrics.generator_releases(canonical, java_rows)
        workload = replace(workload, rows=tuple({**r, "pass_time": releases[r["segment_id"]]} for r in workload.rows))
        release_contract = "same_Java_generator_release_epoch_single_run_sensitivity"
        release_evidence = evidence(args.same_hca_release)
    request, rows, rejected, local = native31.prepare_native_request(native31.case_by_id("t5_2_nanning_1x_speed_2"), workload,
        map_profile_path=native31.DEFAULT_MAP_PROFILE, fault_protocol_path=native31.DEFAULT_FAULT_PROTOCOL, binary=args.binary.resolve())
    if rejected or len(rows) != 43603:
        raise ValueError("no segment filtering permitted")
    overrides = {"s4_wait_estimator": args.s4_wait_estimator}
    request.update(overrides)
    request["trace_limit"] = args.trace_limit
    request["event_trace_limit"] = args.event_trace_limit
    if request.get("enable_edge_capacity_holding", False):
        raise ValueError("edge capacity is excluded by the current user request")
    directory.mkdir(parents=True)
    with gzip.open(directory / "request.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(normalize(request), handle)
    source_paths = [Path(__file__), Path(metrics.__file__), ROOT / "src/czr005/cpp_backend.py", ROOT / "scripts/eval/run_g4irsf31_nanning_native.py", ROOT / "scripts/eval/g4irsf31_map_adapter.py", ROOT / "CMakeLists.txt"]
    source_paths += [p for p in (ROOT / "cpp").rglob("*") if p.is_file() and p.suffix in (".hpp", ".h", ".cpp") and "loaded_transport" not in p.name]
    for path in source_paths:
        frozen = directory / "source" / path.relative_to(ROOT)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, frozen)
    (directory / "binary").mkdir()
    shutil.copyfile(args.binary, directory / "binary" / args.binary.name)
    manifest = {"schema": "g31.feng_alignment.arm.v1", "arm": args.arm, "reused": False,
                "execution_contract": NATIVE_CONTRACT, "release_contract": release_contract, "release_trace": release_evidence,
                "canonical": evidence(CANONICAL), "binary": evidence(args.binary),
                "sources": [evidence(p) for p in source_paths], "score_overrides": overrides,
                "request": evidence(directory / "request.json.gz"), "argv": sys.argv,
                "causality_policy": "independent scheduled EBS segments; no predecessor coupling"}
    write(directory / "manifest.json", manifest)
    started = time.perf_counter()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    manifest["native_call_wall_seconds_excluding_serialization"] = time.perf_counter()-started
    if sha(args.binary) != manifest["binary"]["sha256"]:
        raise ValueError("binary changed during execution")
    with gzip.open(directory / "native_payload.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    manifest["native_payload"] = evidence(directory / "native_payload.json.gz")
    if args.assert_matches_native_payload:
        with gzip.open(args.assert_matches_native_payload, "rt", encoding="utf-8") as handle:
            reference = json.load(handle)
        expected = {r["segment_id"]: r for r in reference["bags"]}
        observed = {r["segment_id"]: r for r in payload["bags"]}
        differences = []
        if set(expected) != set(observed):
            raise ValueError("legacy regression population changed")
        for segment_id, prior in expected.items():
            for key, value in prior.items():
                if observed[segment_id].get(key) != value:
                    differences.append({"segment_id": segment_id, "field": key, "old": value, "new": observed[segment_id].get(key)})
        manifest["legacy_exact_regression"] = {"reference": evidence(args.assert_matches_native_payload), "checked_segments": len(expected),
                                               "all_prior_bag_fields_exactly_equal": not differences, "difference_count": len(differences), "examples": differences[:30]}
        write(directory / "legacy_exact_regression.json", manifest["legacy_exact_regression"])
        if differences:
            write(directory / "manifest.json", manifest)
            raise ValueError("legacy-mode per-segment regression differs; inspect saved raw payload and receipt")
    finish(directory, canonical, metrics.native_segments(payload), manifest, payload["summary"])


def audit_arms(args, *, canonical_path=CANONICAL, horizon=98259.0):
    args.output.mkdir(parents=True, exist_ok=False)
    canonical = metrics.read_jsonl(canonical_path)
    arms, business, segments = {}, {}, {}
    for arg in args.arm:
        name, rawpath = arg.split("=", 1)
        path = Path(rawpath)
        manifest = read(path / "manifest.json")
        if manifest["canonical"]["sha256"] != sha(canonical_path):
            raise ValueError("canonical hash mismatch")
        actual = metrics.read_jsonl(path / "segments.jsonl")
        summary, business[name] = metrics.audit(canonical, actual, horizon=horizon)
        if summary != read(path / "summary.json")["metrics"]:
            raise ValueError("independent recalculation differs from run summary")
        segments[name] = {r["segment_id"]: r for r in actual}
        arms[name] = {"manifest": manifest, "metrics": summary, "evidence": evidence(path / "segments.jsonl")}
    pairs = []
    for left,right in itertools.combinations(arms,2):
        value, rows = metrics.compare(business[left],business[right])
        segment_rows = []
        for s in canonical:
            a,b=segments[left][s["segment_id"]],segments[right][s["segment_id"]]
            segment_rows.append({"segment_id":s["segment_id"],"left_completed":a["completed"],"right_completed":b["completed"],
                                 "observed_delta_left_minus_right":a["finish"]-b["finish"] if a["completed"] and b["completed"] else None,
                                 "restricted_delta_left_minus_right":(a["finish"] if a["completed"] else horizon)-(b["finish"] if b["completed"] else horizon)})
        for suffix,data in [("business",rows),("segments",segment_rows)]:
            with (args.output/f"{left}__{right}_{suffix}.csv").open("w",encoding="utf-8",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
        values=[r["observed_delta_left_minus_right"] for r in segment_rows if r["observed_delta_left_minus_right"] is not None]
        ml,mr=arms[left]["manifest"],arms[right]["manifest"]
        pairs.append({"left":left,"right":right,"same_declared_execution_contract":ml["execution_contract"]==mr["execution_contract"],
                      "same_release_contract":ml["release_contract"]==mr["release_contract"],
                      "full_segment_denominator":len(segment_rows),"both_segments_complete":len(values),
                      "full_population_segment_delta_left_minus_right":metrics.distribution(values) if len(values)==len(segment_rows) else None,
                      "secondary_observed_business_comparison":value,
                      "claim_boundary":"Native Java and mature G31 retain their original execution/source differences; EBS segment independence is intentional and business-causal anomalies remain diagnostic."})
    write(args.output/"audit.json",{"schema":"g31.feng_alignment.comparison.v1","canonical":evidence(canonical_path),
                                    "script":evidence(Path(__file__)),"metrics_script":evidence(Path(metrics.__file__)),"argv":sys.argv,"arms":arms,"pairs":pairs})
    print(json.dumps({"output":str(args.output),"arms":list(arms),"pairs":len(pairs)}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("reuse-baselines")
    run=sub.add_parser("run-native");run.add_argument("--arm",required=True);run.add_argument("--binary",type=Path,required=True)
    run.add_argument("--output",type=Path,required=True);run.add_argument("--s4-wait-estimator",choices=("legacy","eta_calendar","eta_flow"),default="legacy")
    run.add_argument("--assert-matches-native-payload",type=Path)
    run.add_argument("--same-hca-release",type=Path);run.add_argument("--trace-limit",type=int,default=0);run.add_argument("--event-trace-limit",type=int,default=0)
    compare=sub.add_parser("audit");compare.add_argument("--arm",action="append",required=True);compare.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="reuse-baselines":reuse_baselines()
    elif args.command=="run-native":run_native(args)
    else:audit_arms(args)


if __name__=="__main__":main()
