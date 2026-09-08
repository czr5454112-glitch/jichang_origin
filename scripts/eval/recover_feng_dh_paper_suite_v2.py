"""Re-audit a SHA-bound, successful native V6 attempt in a new output directory.

This module never launches or compiles Java. The original attempt remains intact.
The original native command is retained separately from this recovery operation.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_dh_paper_suite_v2 as runner

FILES = ("segments.csv", "bags.csv", "trace.csv", "summary.csv", "event_summary.csv",
         "build_identity.json", "stdout.txt", "stderr.txt", "runner_status.json")
CSV_FILES = FILES[:5]
OLD_RUNNER = ROOT / "scripts/eval/run_feng_dh_paper_suite.py"
OLD_RUNNER_SHA = "f1879d989364e4f9b051d37c85f8458d0e16c5221e3340d529a42e84828de3d6"
read, write, sha, require = runner.read, runner.write, runner.sha, runner.require


def validate_source(spec, output):
    origin = spec["native_recovery_from"]
    source = runner.safe_output(origin["output_dir"])
    output = runner.safe_output(output)
    require(source.parent == output.parent and source != output, "recovery requires a distinct sibling output")
    require(output.name == spec["cell_id"], "recovery output/cell ID mismatch")
    require(set(origin["files_sha256"]) == set(FILES), "incomplete source native manifest")
    for name in FILES:
        require((source / name).resolve().parent == source, "source file traverses a link")
        require(sha(source / name) == origin["files_sha256"][name], "source native file drift: " + name)
    require(Path(origin["runner_path"]).resolve() == OLD_RUNNER and
            origin["runner_sha256"] == sha(OLD_RUNNER) == OLD_RUNNER_SHA, "original runner drift")
    old_path = Path(origin["spec_path"]).resolve(strict=True)
    require(sha(old_path) == origin["spec_sha256"], "original spec drift")
    old = read(old_path)
    ignored = {"cell_id", "native_recovery_from"}
    require({k: v for k, v in old.items() if k not in ignored} ==
            {k: v for k, v in spec.items() if k not in ignored}, "native experiment parameters changed")
    require(old["cell_id"] == source.name and "native_recovery_from" not in old, "invalid original identity")
    require(spec["method"] == runner.METHOD and spec["family"] == "base" and
            spec["horizon_seconds"] == 98259 and spec["timing_policy"] == "full_population_only",
            "recovery outside registered V6 base contract")
    require(sha(spec["protocol_path"]) == spec["protocol_sha256"], "protocol drift")
    status = read(source / "runner_status.json")
    require(status["status"] == "NATIVE_COMPLETE" and status["returncode"] == 0 and
            status["method"] == runner.METHOD and status["runner_sha256"] == OLD_RUNNER_SHA and
            Path(status["spec_path"]).resolve() == old_path and status["spec_sha256"] == sha(old_path) and
            status["protocol_sha256"] == spec["protocol_sha256"], "native execution provenance differs")
    identity_path, identity = runner.external._identity_payload(Path(spec["workload_identity_path"]))
    require(sha(identity_path) == spec["workload_identity_sha256"] and
            all(identity[k] == spec[k] for k in ("map", "load_factor", "seed")), "workload identity drift")
    classes = Path(spec["classes_dir"]).resolve(strict=True)
    build = read(source / "build_identity.json")
    require(sha(source / "build_identity.json") == spec["build_identity_sha256"] and
            build == read(classes / "build_identity.json") and build["method"] == runner.METHOD,
            "build identity drift")
    require(build["source_files"] == runner.file_set(runner.SOURCE, "*.java") and
            build["class_files"] == runner.file_set(classes, "*.class") and
            build["java_sha256"] == sha(runner.JAVA) and build["javac_sha256"] == sha(runner.JAVAC),
            "native source/classes/JDK changed")
    expected_command = [runner.JAVA, "-Xmx1536m", "-cp", str(classes), "App.FengDhBenchmark", "run",
        "--map", identity["map_path"], "--input", identity["raw_path"], "--output", str(source),
        "--speed-mps", str(spec["speed_mps"]), "--horizon-seconds", "98259", "--seed", str(spec["seed"]),
        "--formal-timing-eligible", "true", "--storage-in-goal", str(identity["storage_in_goal"]),
        "--storage-out-start", str(identity["storage_out_start"]), "--trace-sample-modulo", "0"]
    require(status["command"] == expected_command, "actual original native command differs from frozen experiment")
    summary = runner.csv_rows(source / "summary.csv")
    require(len(summary) == 1 and summary[0]["status"] == "HORIZON_REACHED" and
            float(summary[0]["simulation_end_seconds"]) == spec["horizon_seconds"], "wrong native terminal horizon")
    require(summary[0]["method"] == runner.METHOD and
            Path(summary[0]["map_path"]).resolve() == Path(identity["map_path"]).resolve() and
            summary[0]["map_sha256"] == sha(identity["map_path"]) and
            Path(summary[0]["input_path"]).resolve() == Path(identity["raw_path"]).resolve() and
            summary[0]["input_sha256"] == sha(identity["raw_path"]) and
            int(summary[0]["seed"]) == spec["seed"] and
            float(summary[0]["speed_meters_per_second"]) == spec["speed_mps"] and
            float(summary[0]["horizon_seconds"]) == spec["horizon_seconds"] and
            int(summary[0]["initial_blocked_directed_edge_count"]) == 0,
            "native summary input/physical condition identity differs")
    return source, output, identity_path, identity, status


def recover(spec_path, output):
    spec_path = Path(spec_path).resolve(strict=True)
    spec = read(spec_path)
    source, output, identity_path, identity, native_status = validate_source(spec, output)
    require(not output.exists(), "recovery never overwrites an existing attempt")
    started = time.time()
    output.mkdir()
    with (output / "execution.lock").open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    provenance = {"schema": "czr005.dh_parser_recovery.v2", "native_reexecuted": False,
        "reason": "Java N/A clocks are missing values for unfinished bags; old Python parser rejected them.",
        "source": spec["native_recovery_from"], "source_spec_sha256": native_status["spec_sha256"],
        "original_native_command": native_status["command"], "native_runner_sha256": OLD_RUNNER_SHA,
        "normalizer_path": str(Path(runner.__file__).resolve()), "normalizer_sha256": sha(runner.__file__),
        "recovery_tool_path": str(Path(__file__).resolve()), "recovery_tool_sha256": sha(__file__),
        "recovery_command": [sys.executable, str(Path(__file__).resolve()), "--spec", str(spec_path), "--output", str(output)],
        "native_started_at_unix": native_status["started_at_unix"], "native_wall_seconds": native_status["wall_seconds"],
        "recovery_started_at_unix": started}
    status = {"status": "RECOVERY_RUNNING", "method": runner.METHOD, "spec_path": str(spec_path),
        "spec_sha256": sha(spec_path), "protocol_sha256": spec["protocol_sha256"],
        "runner_sha256": sha(runner.__file__), "pid": os.getpid(), "returncode": 0,
        "command": native_status["command"], "started_at_unix": native_status["started_at_unix"],
        "wall_seconds": native_status["wall_seconds"], "native_reexecuted": False,
        "native_runner_sha256": OLD_RUNNER_SHA, "recovery": provenance}
    try:
        write(output / "runner_status.json", status)
        for name in FILES:
            target = output / ("source_runner_status.json" if name == "runner_status.json" else name)
            shutil.copyfile(source / name, target)
            require(sha(target) == spec["native_recovery_from"]["files_sha256"][name], "copied native bytes differ")
        derived = runner.normalize(identity, output)
        bags = derived.pop("bags")
        summary = runner.csv_rows(output / "summary.csv")[0]
        metrics = derived["metrics"]
        require(int(summary["raw_bag_count"]) == metrics["raw_bag_denominator"] and
                int(summary["completed_raw_bags"]) == metrics["completed_raw_bag_count"] and
                int(summary["completed_segments"]) == metrics["completed_segment_count"] and
                int(summary["segment_count"]) == derived["segment_count"],
                "native summary disagrees with recomputation")
        with gzip.open(output / "raw_bag_metrics.jsonl.gz", "wt", encoding="utf-8") as stream:
            for bag in bags:
                stream.write(json.dumps(bag, sort_keys=True, allow_nan=False) + "\n")
        write(output / "population_audit.json", derived)
        archives = []
        for name in CSV_FILES:
            target = output / (name + ".gz")
            with (output / name).open("rb") as src, target.open("wb") as dest, gzip.GzipFile(fileobj=dest, mode="wb", mtime=0) as gz:
                shutil.copyfileobj(src, gz)
            with gzip.open(target, "rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == sha(source / name), "archive changed native bytes")
            archives.append({"file": target.name, "sha256": sha(target), "uncompressed_sha256": sha(source / name)})
        validate_source(spec, output)
        provenance.update(recovery_finished_at_unix=time.time(), original_native_bytes_unchanged=True)
        write(output / "native_recovery.json", provenance)
        result = {"status": "COMPLETE", "method": runner.METHOD, "map": identity["map"],
            "load_factor": identity["load_factor"], "seed": identity["seed"], "speed_mps": spec["speed_mps"],
            "family": spec["family"], "native_status": summary["status"], "spec_sha256": sha(spec_path),
            "workload_identity_sha256": sha(identity_path), "full_population_complete": derived["full_population_complete"],
            "metrics": metrics, "audit_status": "PASS", "survivor_timing_used": False,
            "trace_scope": "complete per-segment terminal states; per-tick tracing disabled; every tick native integrity check",
            "archives": archives, "wall_seconds": native_status["wall_seconds"], "native_reexecuted": False,
            "native_recovery_sha256": sha(output / "native_recovery.json")}
        write(output / "normalized_result.json", result)
        status.update(status="COMPLETE", recovery=provenance, normalized_result_sha256=sha(output / "normalized_result.json"))
        write(output / "runner_status.json", status)
        return result
    except BaseException as exc:
        status.update(status="FAILED_RECOVERY", recovery_error=repr(exc))
        write(output / "runner_status.json", status)
        raise
    finally:
        (output / "execution.lock").unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = recover(args.spec, args.output)
    print(json.dumps({k: result[k] for k in ("status", "native_status", "native_reexecuted", "metrics")}))
