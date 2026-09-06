"""Read-only comparison of five HCA runs before/after Python cleanup changes.

Never calls either runner's normalizer. A process-complete native result is
checked against its own recorded hashes before cross-run comparison.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
METHOD = "HCA_SEGMENT_IDENTITY_V1"
OLD = ROOT / "outputs/runtime/hca_segment_identity_20260906"
NEW = ROOT / "outputs/runtime/hca_segment_identity_20260906_fast_cleanup"
KEYS = (("nanning", 1.0, 155921), ("nanning", 1.0, 181081), ("nanning", 1.0, 232003),
        ("map2", 1.75, 104729), ("nanning", 2.0, 104729))
SCIENTIFIC = ("segment_execution_identity.csv", "release.csv", "routes.csv", "output.txt",
              "outputstarttime.txt", "execution_terminal.csv", "summary.csv", "population_audit.json",
              "segment_lifecycle.csv", "raw_bag_timings.csv")
ZERO_LOGS = {"output.txt": "completed_segment_count", "outputstarttime.txt": "planned_segment_count"}
WALL_COLUMNS = {"wall_seconds", "wall_time_seconds", "elapsed_seconds", "elapsed_ns",
                "windows_per_second", "plans_per_second"}
NORMALIZED_PROVENANCE = {"native_evidence", "workload_identity_path", "generated_at", "normalized_at"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def json_bytes(data):
    return json.loads(data.decode("utf-8-sig"))


def basename(path):
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def cell_dir(root, key):
    map_name, load, seed = key
    return Path(root) / f"{map_name}_{load:.2f}x".replace(".", "p") / f"seed_{seed}" / "hca_segment_identity"


class Evidence:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.cache, self.observed = {}, {}
        path = self.directory / "native_archive/manifest.json"
        self.archive = json_bytes(path.read_bytes()) if path.exists() else None
        self.index = {}
        if self.archive:
            require(self.archive.get("method") == METHOD, "archive method differs")
            for record in self.archive["files"]:
                require(record["source_name"] not in self.index, "duplicate native archive source name")
                self.index[record["source_name"]] = record

    def get(self, name):
        require(basename(name) == name and name not in {".", ".."}, "invalid native evidence name")
        if name in self.cache:
            return self.cache[name]
        direct = self.directory / name
        record = self.index.get(name)
        if direct.exists():
            value = direct.read_bytes()
            observed = {"storage": "NATIVE_FILE", "path": str(direct), "sha256": digest(value)}
            if record is not None:
                require(not record.get("absent") and record["uncompressed_sha256"] == digest(value),
                        "native/archive original digest differs: " + name)
        elif record is not None and not record.get("absent"):
            packed = (self.directory / record["path"]).resolve()
            require(packed.is_relative_to(self.directory / "native_archive"), "archive path escapes native_archive")
            require(file_sha(packed) == record["sha256"], "compressed archive digest differs: " + name)
            value = gzip.decompress(packed.read_bytes())
            require(digest(value) == record["uncompressed_sha256"] and len(value) == record["uncompressed_size_bytes"],
                    "restored archive bytes differ: " + name)
            observed = {"storage": "VERIFIED_GZIP_FALLBACK", "path": str(packed), "sha256": digest(value),
                        "compressed_sha256": record["sha256"]}
        else:
            raise FileNotFoundError(str(direct))
        self.cache[name], self.observed[name] = value, observed
        return value

    def document(self, name):
        return json_bytes(self.get(name))


def input_path(path, directory, name):
    original = Path(path)
    if original.exists():
        return original
    for candidate in (directory / "workload" / name, directory.parent / "workload" / name):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(str(original))


def load_run(evidence, key):
    status = evidence.document("runner_status.json")
    value = evidence.document("normalized_result.json")
    require(status.get("status") == "complete" and status.get("returncode") == 0, "native process did not complete")
    require(value.get("status") == "COMPLETE" and status.get("method") == value.get("method") == METHOD,
            "wrong result/method")
    require((value["map"], float(value["load_factor"]), int(value["seed"])) == key, "wrong cell coordinate")
    require(value["fixed_horizon_seconds"] == status["horizon_seconds"] == 98259.0, "fixed horizon differs")
    recorded = {}
    for record in value["native_evidence"]:
        name = basename(record["path"])
        require(name not in recorded, "duplicate normalized native evidence name")
        require(str(record["path"]).replace("\\", "/").rsplit("/", 1)[0] ==
                str(status["cwd"]).replace("\\", "/").rstrip("/"), "native evidence points outside its recorded run")
        data = evidence.get(name)
        require(digest(data) == record["sha256"] and len(data) == record["size_bytes"],
                "recorded native evidence was modified: " + name)
        recorded[name] = record["sha256"]
    audit = evidence.document("population_audit.json")
    require(audit == value["population_audit"] and audit["status"] == "PASS", "population audit differs from normalized record")
    for name in (*SCIENTIFIC, "runner_status.json", "build_identity.json"):
        if name not in recorded and name in ZERO_LOGS:
            require(audit[ZERO_LOGS[name]] == 0 and name in audit.get("absent_zero_event_logs", []),
                    "missing log lacks native zero-event audit: " + name)
            require(not (evidence.directory / name).exists(), "claimed absent log exists")
        else:
            require(name in recorded, "normalized record omitted required evidence: " + name)
    build = evidence.document("build_identity.json")
    contract = value["normalization_contract"]
    require(digest(evidence.get("build_identity.json")) == status["build_identity_sha256"] == contract["build_identity_sha256"],
            "native build manifest differs")
    require(build["method"] == METHOD, "build method differs")
    for field, normalized_field in (("source_sha256", "reconstruction_java_source_sha256"),
                                    ("class_sha256", "compiled_java_class_sha256")):
        records = build["source_files" if field == "source_sha256" else "class_files"]
        bound = digest("".join(r["path"] + "\0" + r["sha256"] + "\n" for r in records).encode())
        require(bound == build[field] == status[field] == contract[normalized_field], "Java identity differs: " + field)
    require(status["protocol_sha256"] == contract["protocol_sha256"], "internal protocol identity differs")
    identity_path = input_path(value["workload_identity_path"], evidence.directory, "identity.json")
    identity = json_bytes(identity_path.read_bytes())
    identity_sha = file_sha(identity_path)
    require(identity_sha == value["workload_identity_sha256"] == status["workload_identity_sha256"], "input identity differs")
    inputs = {"identity": identity_sha}
    for field, name in (("raw", "inputdata.txt"), ("canonical", "canonical.jsonl"), ("map", "map.txt")):
        path = input_path(identity[field + "_path"], evidence.directory, name)
        actual = file_sha(path)
        require(actual == identity[field + "_sha256"] == value["workload_" + field + "_sha256"] == status["inputs"][field]["sha256"],
                "input file digest differs: " + field)
        inputs[field] = actual
    command = status["command"]
    require(command.count("HcaSegmentIdentityBenchmark") == 1, "wrong native Java command")
    arguments = command[command.index("HcaSegmentIdentityBenchmark") + 1:]
    require(len(arguments) == 20, "native Java argument schema differs")
    scientific_arguments = {str(i): arguments[i] for i in (2, 3, 4, 5, 6, 9, 10, 11, 13, 14, 15, 16, 17)}
    return {"status": status, "normalized": value, "build": build, "inputs": inputs,
            "scientific_arguments": scientific_arguments, "recorded": recorded,
            "canonical_java_command": [str(arg).replace(status["cwd"], "{OUTPUT}") for arg in command]}


def scientific_summary(data):
    table = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    excluded = sorted({field for row in table for field in row if field in WALL_COLUMNS})
    return [{key: value for key, value in row.items() if key not in WALL_COLUMNS} for row in table], excluded


def compare_pair(old_dir, new_dir, key):
    require(Path(old_dir).resolve() != Path(new_dir).resolve(), "comparison must use two distinct runs")
    old, new = Evidence(old_dir), Evidence(new_dir)
    for label, evidence in (("old", old), ("new", new)):
        try:
            state = evidence.document("runner_status.json")
            evidence.get("normalized_result.json")
        except FileNotFoundError:
            return {"status": "INCOMPLETE", "unavailable_side": label, "reason": "normalized result or native status unavailable"}
        if state.get("status") == "running":
            return {"status": "INCOMPLETE", "unavailable_side": label, "reason": "native process still running"}
    left, right = load_run(old, key), load_run(new, key)
    for field in ("inputs", "build", "scientific_arguments", "canonical_java_command"):
        require(left[field] == right[field], "cross-run " + field + " differs")
    require(old.get("build_identity.json") == new.get("build_identity.json"), "Java build manifest bytes differ")
    for field in ("python_executable", "python_version"):
        require(left["status"].get(field) == right["status"].get(field), "Python runtime differs: " + field)
    require(left["status"]["protocol_sha256"] == right["status"]["protocol_sha256"], "protocol changed; not cleanup-only")
    compared, excluded = {}, []
    for name in SCIENTIFIC:
        if name not in left["recorded"] or name not in right["recorded"]:
            require(name in ZERO_LOGS and name not in left["recorded"] and name not in right["recorded"],
                    "zero-event log presence differs: " + name)
            compared[name] = {"comparison": "BOTH_ABSENT_WITH_ZERO_EVENT_AUDIT"}
            continue
        a, b = old.get(name), new.get(name)
        if name == "summary.csv":
            sa, excluded_a = scientific_summary(a)
            sb, excluded_b = scientific_summary(b)
            require(excluded_a == excluded_b and sa == sb, "summary scientific columns differ")
            excluded = excluded_a
        if name != "summary.csv" or not excluded:
            require(a == b, "scientific evidence bytes differ: " + name)
        compared[name] = {"old_sha256": digest(a), "new_sha256": digest(b),
                          "comparison": "SCIENTIFIC_COLUMNS_EQUAL" if name == "summary.csv" and excluded else "BYTES_EQUAL"}
    left_science = {k: v for k, v in left["normalized"].items() if k not in NORMALIZED_PROVENANCE}
    right_science = {k: v for k, v in right["normalized"].items() if k not in NORMALIZED_PROVENANCE}
    require(left_science == right_science, "normalized scientific result/metrics/contract differs")
    provenance = {}
    for label, loaded, evidence in (("old", left, old), ("new", right, new)):
        status = loaded["status"]
        provenance[label] = {key: status.get(key) for key in ("python_runner_sha256", "python_executable", "python_version",
            "started_at", "finished_at", "wall_seconds", "cwd", "protocol_sha256", "source_sha256", "class_sha256", "build_identity_sha256")}
        provenance[label].update(runner_status_sha256=digest(evidence.get("runner_status.json")),
                                normalized_result_sha256=digest(evidence.get("normalized_result.json")),
                                workload_identity_path=loaded["normalized"]["workload_identity_path"],
                                evidence_storage=evidence.observed)
    return {"status": "PASS", "inputs": left["inputs"], "scientific_files": compared,
            "summary_excluded_wall_columns": excluded, "metrics_equal": True, "population_audit_bytes_equal": True,
            "java_build_bytes_equal": old.get("build_identity.json") == new.get("build_identity.json"),
            "python_runner_identity_changed": provenance["old"]["python_runner_sha256"] != provenance["new"]["python_runner_sha256"],
            "provenance": provenance}


def audit(old_root=OLD, new_root=NEW):
    cells, failures, missing = [], [], []
    for key in KEYS:
        coordinate = dict(zip(("map", "load_factor", "seed"), key))
        try:
            result = compare_pair(cell_dir(old_root, key), cell_dir(new_root, key), key)
            cells.append(dict(coordinate, **result))
            if result["status"] == "INCOMPLETE":
                missing.append(coordinate)
        except Exception as error:
            failures.append(dict(coordinate, error=type(error).__name__ + ": " + str(error)))
    return {"schema": "czr005.hca_postprocessing_equivalence.v1",
            "status": "FAIL" if failures else "INCOMPLETE" if missing else "PASS",
            "expected_paired_cells": 5, "passed_paired_cells": sum(c["status"] == "PASS" for c in cells),
            "old_root": str(Path(old_root).resolve()), "new_root": str(Path(new_root).resolve()),
            "cells": cells, "missing_cells": missing, "failures": failures,
            "old_preflight_cells_in_final_matrix": 0, "duplicate_selection_by_performance": False,
            "protocol_difference_allowed": False,
            "allowed_differences": ["Python runner identity", "working/output paths", "actual execution timestamps and wall time"],
            "scope": "Five fixed-coordinate byte/identity equivalence checks, not a new simulator validation or a duplicate result selection.",
            "normalizer_called": False, "original_evidence_modified": False, "simulations_started": 0,
            "auditor_sha256": file_sha(Path(__file__)), "audited_at": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-root", type=Path, default=OLD)
    parser.add_argument("--new-root", type=Path, default=NEW)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.old_root, args.new_root)
    output = args.output or args.new_root / "preflight/postprocessing_equivalence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("status", "passed_paired_cells", "expected_paired_cells", "missing_cells", "failures")}))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
