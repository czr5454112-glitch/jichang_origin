"""Reproducible formal-OD coverage and strict map2 full-population repair regression."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/runtime/feng_cie_dh_zero_through_repair_20260905/regression"
OLD_SHA = "99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8"
OLD_COMMIT = "f101c2f6c21bd4a147e060ba09bf95b26b48b50c"
CORE = ROOT / "benchmarks/java/feng_cie_dh/App"
HARNESS = ROOT / "benchmarks/java/feng_cie_dh_audit/App/FengDhOdAudit.java"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.relative_to(root).as_posix()):
        name, content = path.relative_to(root).as_posix().encode(), path.read_bytes()
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(content).to_bytes(8, "big")); digest.update(content)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare_old() -> None:
    destination = ROOT / "tmp/feng_zero_through_old_sources/App"
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    for source in sorted(CORE.glob("*.java")):
        content = subprocess.run(["git", "show", f"{OLD_COMMIT}:benchmarks/java/feng_cie_dh/App/{source.name}"],
                                 cwd=ROOT, check=True, capture_output=True).stdout
        path = destination / source.name
        path.write_bytes(content)
        files.append(path)
    assert aggregate(files, destination.parent) == OLD_SHA
    write_json(OUT / "old_source_identity.json", {"commit": OLD_COMMIT,
        "source_aggregate_sha256": OLD_SHA,
        "files": {p.name: sha(p) for p in files},
        "recovery": "Read-only git show of the audited commit; copied outside production source."})


def prepare() -> None:
    ods: dict[str, dict[tuple[int, int], list[object]]] = {"map2": {}, "nanning": {}}
    coverage = []
    identities = sorted((ROOT / "data/processed/workloads/cie_external_robustness").glob("*/seed_*/identity.json"))
    assert len(identities) == 60, len(identities)
    for identity_path in identities:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        raw = Path(identity["raw_path"])
        assert sha(raw) == identity["raw_sha256"], raw
        raw_count = segment_count = 0
        cell_ods: set[tuple[int, int]] = set()
        with raw.open(encoding="utf-8") as handle:
            next(handle)
            for line in handle:
                if not line.strip(): continue
                fields = line.split()
                raw_count += 1
                start, goal = int(fields[3]), int(fields[4])
                early = float(fields[2]) - float(fields[1]) >= 4800.0
                pairs = [(start, identity["storage_in_goal"]), (identity["storage_out_start"], goal)] if early else [(start, goal)]
                for segment, od in enumerate(pairs):
                    segment_count += 1
                    cell_ods.add(od)
                    ods[identity["map"]].setdefault(od, [*od, fields[0], segment,
                        raw.relative_to(ROOT).as_posix(), line.strip()])
        assert raw_count == identity["raw_bag_count"]
        assert segment_count == identity["segment_count"]
        coverage.append({"identity_path": identity_path.relative_to(ROOT).as_posix(),
                         "identity_sha256": sha(identity_path), "raw_sha256": sha(raw),
                         "raw_bags": raw_count, "segments": segment_count,
                         "unique_od_count": len(cell_ods), "map": identity["map"]})
    # Original Table 5.3 workload is also covered, separately from randomized cells.
    schedule = ROOT / "data/processed/feng_table53_segment_schedule.csv"
    original_ods = set()
    with schedule.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            od = int(row["start"]), int(row["goal"])
            original_ods.add(od)
            assert od in ods["map2"], od
    OUT.mkdir(parents=True, exist_ok=True)
    for map_name, records in ods.items():
        with (OUT / f"{map_name}_formal_ods.tsv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["start", "goal", "raw_bag_id", "segment_id", "input_path", "raw_row"])
            writer.writerows(records[k] for k in sorted(records))
    with (OUT / "nanning_topology_witness.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "goal", "raw_bag_id", "segment_id", "input_path", "raw_row"])
        writer.writerow([130, 58, "TOPOLOGY_ONLY", 0, "data/processed/maps/nanning_legacy.txt", ""])
    write_json(OUT / "formal_od_coverage.json", {
        "schema": "czr005.feng_zero_through_formal_od_coverage.v1",
        "derivation": "Expand every raw row from all 60 frozen cells with the unchanged Java early/EBS contract; deduplicate by directed OD only for independent single-bag tests.",
        "source_cells": coverage, "unique_formal_ods": {k: len(v) for k, v in ods.items()},
        "original_table53_unique_ods": len(original_ods), "original_table53_schedule_sha256": sha(schedule),
        "single_bag_release_tick": 0, "purpose": "NO_CONGESTION_CORRECTNESS_ONLY_NOT_PERFORMANCE"})
    print(json.dumps({k: len(v) for k, v in ods.items()}))


def audit(version: str, source_dir: Path) -> None:
    sources = sorted(source_dir.glob("*.java"))
    source_sha = aggregate(sources, source_dir.parent)
    if version == "old": assert source_sha == OLD_SHA, source_sha
    classes = ROOT / f"build/feng_zero_through_audit_{OUT.name}_{version}"
    classes.mkdir(parents=True, exist_ok=True)
    subprocess.run([shutil.which("javac") or "javac", "--release", "8", "-encoding", "UTF-8", "-d", str(classes),
                    *map(str, sources), str(HARNESS)], check=True, cwd=ROOT)
    results = {}
    for name in ("map2", "nanning", "nanning_topology_witness"):
        map_path = ROOT / ("legacy/jichang_origin_readonly/map2.txt" if name == "map2" else "data/processed/maps/nanning_legacy.txt")
        od_file = OUT / (f"{name}_formal_ods.tsv" if name != "nanning_topology_witness" else f"{name}.tsv")
        result_path = OUT / f"{version}_{name}_single_bag.jsonl"
        command = [shutil.which("java") or "java", "-Xmx1g", "-cp", str(classes), "App.FengDhOdAudit", str(map_path), str(od_file), str(result_path)]
        if version != "old": command.append("require-pass")
        started = time.perf_counter()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        records = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
        reachable = [r for r in records if r["reachable"]]
        results[name] = {"count": len(records), "reachable": len(reachable),
            "completed": sum(r["status"] == "COMPLETE" for r in reachable),
            "zero_intermediate_od_count": sum(bool(r["zero_intermediate_nodes"]) for r in reachable),
            "zero_goal_od_count": sum(r["zero_goal"] for r in reachable),
            "repeated_zero_service_starts": sum(r["repeated_zero_service_starts"] for r in reachable),
            "wall_seconds": time.perf_counter() - started, "returncode": run.returncode,
            "stdout": run.stdout, "stderr": run.stderr, "evidence_sha256": sha(result_path),
            "map_sha256": sha(map_path), "od_file_sha256": sha(od_file)}
    write_json(OUT / f"{version}_single_bag_summary.json", {
        "source_aggregate_sha256": source_sha, "harness_sha256": sha(HARNESS),
        "class_aggregate_sha256": aggregate(list(classes.rglob("*.class")), classes),
        "version": version, "results": results})
    nanning = [json.loads(line) for line in (OUT / f"{version}_nanning_single_bag.jsonl").read_text(encoding="utf-8").splitlines()]
    witness = next(r for r in nanning if r.get("zero_intermediate_nodes"))
    write_json(OUT / f"{version}_formal_business_witness.json", witness)
    print(json.dumps(results, indent=2))
    if version != "old": assert all(r["returncode"] == 0 for r in results.values())


def regression() -> None:
    baseline = ROOT / "outputs/runtime/feng_cie_dh_reconstruction/primary"
    destination = OUT / "map2_full_population_repaired"
    classes = ROOT / f"build/feng_zero_through_{OUT.name}"
    command = [sys.executable, str(ROOT / "scripts/eval/run_feng_paper_env_cie_dh.py"), "run",
               "--classes-dir", str(classes), "--output-dir", str(destination)]
    subprocess.run(command, cwd=ROOT, check=True)
    comparisons = {}
    for name in ("bags.csv", "segments.csv", "event_summary.csv", "trace.csv"):
        old, new = baseline / name, destination / name
        comparisons[name] = {"old_sha256": sha(old), "new_sha256": sha(new), "byte_identical": old.read_bytes() == new.read_bytes()}
        if name in ("bags.csv", "segments.csv"):
            with new.open(encoding="utf-8", newline="") as handle:
                records = list(csv.DictReader(handle))
            comparisons[name]["rows"] = len(records)
            expected = 28506 if name == "bags.csv" else 43603
            assert len(records) == expected
    with (baseline / "summary.csv").open(encoding="utf-8", newline="") as h: before = next(csv.DictReader(h))
    with (destination / "summary.csv").open(encoding="utf-8", newline="") as h: after = next(csv.DictReader(h))
    differences = {k: {"old": before.get(k), "new": after.get(k)} for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    report = {"schema": "czr005.feng_zero_through_map2_full_population_regression.v1",
              "baseline_status_sha256": sha(baseline / "runner_status.json"),
              "repaired_status_sha256": sha(destination / "runner_status.json"),
              "baseline_source_sha256": json.loads((baseline / "runner_status.json").read_text())["identity"]["reconstruction_java_source_aggregate_sha256"],
              "repaired_source_sha256": json.loads((destination / "runner_status.json").read_text())["identity"]["reconstruction_java_source_aggregate_sha256"],
              "file_comparisons": comparisons, "summary_differences": differences,
              "allowed_summary_difference_fields": ["wall_seconds"],
              "pass": all(v["byte_identical"] for v in comparisons.values()) and set(differences) <= {"wall_seconds"}}
    write_json(OUT / "map2_full_population_regression.json", report)
    print(json.dumps(report, indent=2))
    assert report["pass"], "repair changed map2 behavior"


def summarize() -> None:
    rows, archives = [], []
    unaffected = 0
    for name in ("map2", "nanning", "nanning_topology_witness"):
        versions = {}
        for version in ("old", "repaired"):
            path = OUT / f"{version}_{name}_single_bag.jsonl"
            content = path.read_bytes()
            versions[version] = [json.loads(line) for line in content.decode("utf-8").splitlines()]
            archive = path.with_suffix(".jsonl.gz")
            archive.write_bytes(gzip.compress(content, mtime=0))
            archives.append({"path": archive.relative_to(ROOT).as_posix(),
                             "sha256": sha(archive), "uncompressed_sha256": sha(path)})
        assert len(versions["old"]) == len(versions["repaired"])
        for old, new in zip(versions["old"], versions["repaired"]):
            assert (old["start"], old["goal"]) == (new["start"], new["goal"])
            assert new["status"] == "COMPLETE" and new["first_invalid_state"] is None
            identical = old == new
            if not old["zero_intermediate_nodes"]:
                assert identical, (name, old["start"], old["goal"])
                unaffected += 1
            rows.append({"map": name, "start": old["start"], "goal": old["goal"],
                "old_status": old["status"], "repaired_status": new["status"],
                "old_end_tick": old["end_tick"], "repaired_completion_tick": new["completion_tick"],
                "zero_intermediate_nodes": ";".join(map(str, old["zero_intermediate_nodes"])),
                "zero_goal": old["zero_goal"], "entire_audit_record_identical": identical,
                "old_first_invalid_tick": (old["first_invalid_state"] or {}).get("tick", ""),
                "old_first_invalid_node": (old["first_invalid_state"] or {}).get("node", ""),
                "sample_raw_bag_id": old["sample_raw_bag_id"],
                "sample_segment_id": old["sample_segment_id"]})
    with (OUT / "single_bag_od_comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    write_json(OUT / "single_bag_equivalence_and_archives.json", {
        "pass": True, "complete_repaired_od_tests": len(rows),
        "unchanged_positive_intermediate_od_records": unaffected,
        "old_failure_stop_rule": "Stop immediately after observing the second consecutive invalid zero-service restart; FAILED is an audit verdict, not a production horizon status.",
        "release_time_note": "Every isolated test resets release to tick 0. Formal business identities and exact raw source rows are retained, but these are correctness tests, not population performance measurements.",
        "archives": archives})
    print(json.dumps({"pass": True, "repaired": len(rows), "unchanged": unaffected}))


def compare_reference(reference: Path) -> None:
    """Require all sampled service traces and the complete map2 population to match."""
    comparisons = {}
    names = [f"repaired_{name}_single_bag.jsonl" for name in
             ("map2", "nanning", "nanning_topology_witness")]
    names += [f"map2_full_population_repaired/{name}" for name in
              ("bags.csv", "segments.csv", "event_summary.csv", "trace.csv")]
    for name in names:
        before, after = reference / name, OUT / name
        comparisons[name] = {"reference_sha256": sha(before), "current_sha256": sha(after),
                             "byte_identical": before.read_bytes() == after.read_bytes()}
    native = "map2_full_population_repaired"
    with (reference / native / "summary.csv").open(encoding="utf-8", newline="") as h:
        before_summary = next(csv.DictReader(h))
    with (OUT / native / "summary.csv").open(encoding="utf-8", newline="") as h:
        after_summary = next(csv.DictReader(h))
    differences = {k: {"reference": before_summary.get(k), "current": after_summary.get(k)}
                   for k in before_summary.keys() | after_summary.keys()
                   if before_summary.get(k) != after_summary.get(k)}
    reference_identity = json.loads((reference / native / "runner_status.json").read_text())["identity"]
    current_identity = json.loads((OUT / native / "runner_status.json").read_text())["identity"]
    report = {"schema": "czr005.feng_correctness_to_optimized_equivalence.v1",
              "reference_directory": reference.relative_to(ROOT).as_posix(),
              "reference_source_sha256": reference_identity["reconstruction_java_source_aggregate_sha256"],
              "current_source_sha256": current_identity["reconstruction_java_source_aggregate_sha256"],
              "reference_class_sha256": reference_identity["compiled_java_class_aggregate_sha256"],
              "current_class_sha256": current_identity["compiled_java_class_aggregate_sha256"],
              "file_comparisons": comparisons, "summary_differences": differences,
              "allowed_summary_difference_fields": ["wall_seconds"],
              "pass": all(v["byte_identical"] for v in comparisons.values()) and set(differences) <= {"wall_seconds"}}
    write_json(OUT / "correctness_to_optimized_equivalence.json", report)
    print(json.dumps(report, indent=2))
    assert report["pass"], "optimization changed service traces or population behavior"


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "prepare-old", "audit", "regression", "summarize", "compare-reference"])
    parser.add_argument("--version", default="repaired")
    parser.add_argument("--source-dir", type=Path, default=CORE)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    if args.action == "prepare": prepare()
    elif args.action == "prepare-old": prepare_old()
    elif args.action == "audit": audit(args.version, args.source_dir.resolve())
    elif args.action == "summarize": summarize()
    elif args.action == "compare-reference":
        if args.reference_dir is None: parser.error("compare-reference requires --reference-dir")
        compare_reference(args.reference_dir.resolve())
    else: regression()


if __name__ == "__main__": main()
