"""Independent V6 runner: real uniform speeds, known all-day faults, full bag audit."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external

METHOD = "FENG_DH_PAPER_SUITE_V6"
SOURCE = ROOT / "benchmarks/java/feng_cie_dh_paper_suite_v6/App"
BUILD = ROOT / "build/feng_dh_paper_suite_v6_20260907"
JAVA = r"C:\PROGRAMING\jdk-18\bin\java.exe"
JAVAC = r"C:\PROGRAMING\jdk-18\bin\javac.exe"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_set(root, pattern):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob(pattern))}


def compile_build(classes=BUILD):
    classes = Path(classes).resolve()
    target = classes / "build_identity.json"
    sources = file_set(SOURCE, "*.java")
    if target.exists():
        value = read(target)
        require(value["method"] == METHOD and value["source_files"] == sources, "build/source drift")
        require(value["class_files"] == file_set(classes, "*.class"), "compiled classes drift")
        require(value["java_sha256"] == sha(JAVA) and value["javac_sha256"] == sha(JAVAC), "JDK drift")
        return value
    require(not classes.exists() or not any(classes.iterdir()), "compile requires empty new directory")
    classes.mkdir(parents=True, exist_ok=True)
    command = [JAVAC, "-encoding", "UTF-8", "-d", str(classes), *map(str, sorted(SOURCE.glob("*.java")))]
    subprocess.run(command, check=True, capture_output=True)
    value = {"method": METHOD, "source_files": sources, "class_files": file_set(classes, "*.class"),
             "java_sha256": sha(JAVA), "javac_sha256": sha(JAVAC), "compile_command": command,
             "reconstruction": "SEMANTICALLY_PARTIAL_V5_WITH_UNIFORM_PHYSICAL_SPEED_AND_INITIAL_FAULT_EXTENSION"}
    write(target, value)
    return value


def safe_output(path):
    original = Path(path).absolute()
    resolved = original.resolve()
    require(original == resolved and resolved.is_relative_to(ROOT), "output outside workspace or through junction")
    parts = resolved.relative_to(ROOT).parts
    require((len(parts) >= 3 and parts[:2] == ("outputs", "runtime") and "paper_suite" in parts[2]) or
            (len(parts) >= 2 and parts[0] == "tmp" and "paper_suite" in parts[1]), "new suite namespace required")
    return resolved


def csv_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def finite_or_none(value):
    return float(value) if value not in ("", "NaN", "nan", None) else None


def normalize(identity, output):
    canonical = [json.loads(line) for line in Path(identity["canonical_path"]).read_text(encoding="utf-8").splitlines()]
    expected = {(int(row["task_id"]), 1 if row["leg"] == "storage_out" else 0): row for row in canonical}
    require(len(expected) == len(canonical), "duplicate canonical key")
    native = csv_rows(output / "segments.csv")
    by_key = {(int(row["source_raw_bag_id"]), int(row["segment_id"])): row for row in native}
    require(len(native) == len(by_key) and set(by_key) == set(expected), "native exact population mismatch")
    per_bag = defaultdict(list)
    completed_segments = 0
    for key, can in expected.items():
        row = by_key[key]
        require(int(row["start"]) == int(can["start"]) and int(row["goal"]) == int(can["goal"]), "native OD mismatch")
        require(abs(float(row["release_seconds"])-float(can["pass_time"])) < 1e-6, "canonical D mismatch")
        finish = finite_or_none(row["completion_time_seconds"])
        admission = finite_or_none(row["admission_time_seconds"])
        require((finish is not None) == (row["status"] == "COMPLETED"), "completion state mismatch")
        if finish is not None:
            require(int(row["final_node"]) == int(can["goal"]), "completion at wrong destination")
            require(admission is not None and float(can["pass_time"])-1e-6 <= admission <= finish <= 98259+1e-6,
                    "causal time or fixed horizon violation")
            completed_segments += 1
        per_bag[key[0]].append({"segment_id": can["segment_id"], "finish": finish, "admission": admission,
                               "D": float(can["pass_time"]), "std": float(can["std"]), "state": row["status"]})
    bags = []
    for task, segments in sorted(per_bag.items()):
        complete = all(s["finish"] is not None for s in segments)
        finish = max(s["finish"] for s in segments) if complete else None
        std = segments[0]["std"]
        bags.append({"task_id": task, "segment_count": len(segments), "complete": complete,
                     "finish_seconds": finish, "std_seconds": std,
                     "tht_D_seconds": sum(s["finish"]-s["D"] for s in segments) if complete else None,
                     "tht_native_seconds": sum(s["finish"]-s["admission"] for s in segments) if complete else None,
                     "on_time_std": complete and finish <= std+1e-9,
                     "on_time_paper_literal": complete and finish <= std-2700+1e-9})
    denominator = int(identity["raw_bag_count"])
    require(len(bags) == denominator, "raw bag denominator mismatch")
    done = sum(b["complete"] for b in bags)
    full = done == denominator
    values = [b["tht_D_seconds"] for b in bags] if full else []
    native_values = [b["tht_native_seconds"] for b in bags] if full else []
    metrics = {"raw_bag_denominator": denominator, "completed_raw_bag_count": done,
               "unfinished_raw_bag_count": denominator-done, "completed_segment_count": completed_segments,
               "completion_rate": done/denominator,
               "success_rate_std": sum(b["on_time_std"] for b in bags)/denominator,
               "success_rate_paper_literal": sum(b["on_time_paper_literal"] for b in bags)/denominator,
               "tht_D_min_seconds": min(values) if full else None,
               "tht_D_mean_seconds": math.fsum(values)/denominator if full else None,
               "tht_D_max_seconds": max(values) if full else None,
               "tht_native_min_seconds": min(native_values) if full else None,
               "tht_native_mean_seconds": math.fsum(native_values)/denominator if full else None,
               "tht_native_max_seconds": max(native_values) if full else None,
               "completed_raw_bags_per_fixed_horizon_hour": done*3600/98259}
    return {"status": "PASS", "exact_segment_population": True, "completed_goal_check": True,
            "full_population_complete": full, "segment_count": len(native), "metrics": metrics,
            "bags": bags}


def run_spec(spec_path, output_dir):
    spec_path = Path(spec_path).resolve(strict=True)
    spec = read(spec_path)
    require(spec["method"] == METHOD and spec["timing_policy"] == "full_population_only", "wrong method/timing policy")
    require(spec["family"] in ("base", "all_day_fault"), "unsupported family, no silent fallback")
    for unsupported in ("fault_schedule", "repairs", "repair_time", "repair_epoch", "bias_fraction",
                        "physical_disturbance", "message_delay_seconds", "drop_notification"):
        require(spec.get(unsupported) in (None, False, 0, [], {}), "unsupported condition: " + unsupported)
        require(spec.get("scenario", {}).get(unsupported) in (None, False, 0, [], {}),
                "unsupported scenario condition: " + unsupported)
    if spec["family"] == "all_day_fault":
        require(spec.get("fault_notification_epoch") == 8260, "only first-round-known all-day failures supported")
        failed = spec.get("failed_edges", [])
        initial = spec.get("initial_failed_edges", [])
        require(failed and len({tuple(edge) for edge in failed}) == len(failed), "duplicate/missing disabled edges")
        require(initial and {tuple(edge) for edge in initial} <= {tuple(edge) for edge in failed},
                "initial fault edges missing from disabled closure")
        require(spec.get("scenario", {}).get("fault_edges") == failed, "fault-edge contracts disagree")
    require(spec["speed_mps"] in (1.5, 2.5, 3.0) and spec["horizon_seconds"] == 98259, "unregistered speed/horizon")
    identity_path = Path(spec["workload_identity_path"]).resolve(strict=True)
    require(sha(identity_path) == spec["workload_identity_sha256"], "workload identity drift")
    identity_path, identity = external._identity_payload(identity_path)
    require(identity["seed"] == spec["seed"] and identity["load_factor"] in (1., 2.), "seed/load mismatch")
    require(sha(spec["protocol_path"]) == spec["protocol_sha256"], "protocol drift")
    classes = Path(spec.get("classes_dir", BUILD)).resolve(strict=True)
    build = compile_build(classes)
    output = safe_output(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "execution.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        require(not (output / "runner_status.json").exists(), "prior attempt exists; never overwrite scientific evidence")
        command = [JAVA, "-Xmx1536m", "-cp", str(classes), "App.FengDhBenchmark", "run",
                   "--map", identity["map_path"], "--input", identity["raw_path"], "--output", str(output),
                   "--speed-mps", str(spec["speed_mps"]), "--horizon-seconds", "98259",
                   "--seed", str(spec["seed"]), "--formal-timing-eligible", "true",
                   "--storage-in-goal", str(identity["storage_in_goal"]),
                   "--storage-out-start", str(identity["storage_out_start"]), "--trace-sample-modulo", "0"]
        failed = spec.get("failed_edges", [])
        if spec["family"] == "all_day_fault":
            require(failed and spec["scenario"]["information_contract"] == "KNOWN_SURVIVING_TOPOLOGY_NO_SOURCE_PREFILTER",
                    "fault information contract missing")
            command += ["--blocked-edges", ";".join(f"{u}:{v}" for u, v in failed)]
        else:
            require(not failed, "fault edge in base case")
        status = {"status": "RUNNING", "method": METHOD, "spec_path": str(spec_path), "spec_sha256": sha(spec_path),
                  "protocol_sha256": spec["protocol_sha256"], "command": command, "pid": os.getpid(),
                  "started_at_unix": time.time(), "runner_sha256": sha(__file__)}
        write(output / "runner_status.json", status)
        write(output / "build_identity.json", build)
        with (output / "stdout.txt").open("w", encoding="utf-8") as stdout, (output / "stderr.txt").open("w", encoding="utf-8") as stderr:
            process = subprocess.run(command, cwd=output, stdout=stdout, stderr=stderr)
        status.update(returncode=process.returncode, wall_seconds=time.time()-status["started_at_unix"],
                      status="NATIVE_COMPLETE" if process.returncode == 0 else "FAILED_NATIVE")
        write(output / "runner_status.json", status)
        require(process.returncode == 0, "native Java failure, evidence retained")
        derived = normalize(identity, output)
        bags = derived.pop("bags")
        with gzip.open(output / "raw_bag_metrics.jsonl.gz", "wt", encoding="utf-8") as stream:
            for bag in bags:
                stream.write(json.dumps(bag, sort_keys=True, allow_nan=False)+"\n")
        write(output / "population_audit.json", derived)
        archive = []
        for name in ("segments.csv", "bags.csv", "trace.csv", "summary.csv", "event_summary.csv"):
            source = output / name
            target = output / (name + ".gz")
            with source.open("rb") as source_stream, target.open("wb") as destination, gzip.GzipFile(fileobj=destination, mode="wb", mtime=0) as compressed:
                shutil.copyfileobj(source_stream, compressed)
            with gzip.open(target, "rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == sha(source), "archive mismatch")
            archive.append({"file": target.name, "sha256": sha(target), "uncompressed_sha256": sha(source)})
        native_summary = csv_rows(output / "summary.csv")[0]
        result = {"status": "COMPLETE", "method": METHOD, "map": identity["map"], "load_factor": identity["load_factor"],
                  "seed": identity["seed"], "speed_mps": spec["speed_mps"], "family": spec["family"],
                  "native_status": native_summary["status"], "spec_sha256": sha(spec_path),
                  "workload_identity_sha256": sha(identity_path), "full_population_complete": derived["full_population_complete"],
                  "metrics": derived["metrics"], "audit_status": "PASS", "survivor_timing_used": False,
                  "trace_scope": "complete per-segment terminal states; per-tick tracing disabled; every tick native integrity check",
                  "archives": archive, "wall_seconds": status["wall_seconds"]}
        write(output / "normalized_result.json", result)
        status["status"] = "COMPLETE"
        write(output / "runner_status.json", status)
        return result
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("compile", "run"))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compile_build() if args.mode == "compile" else run_spec(args.spec, args.output)
    print(json.dumps({k: result[k] for k in ("status", "method", "full_population_complete") if k in result}))


if __name__ == "__main__":
    main()
