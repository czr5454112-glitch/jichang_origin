"""Prepare/run unchanged Feng Java HCA on the complete original map2 1x queue."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.eval import run_g4irsf24_fresh_hca as runner
from czr005.io.legacy_map import parse_legacy_map
from czr005.io.legacy_tasks import parse_legacy_tasks, expand_tasks

DEFAULT_ORIGINAL = Path(r"C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目\代码-ICSsimulation")
DEFAULT_OUTPUT = ROOT / "outputs/experiments/g31_feng_alignment_map2_20261023/java_native_1x"
CANONICAL = ROOT / "data/processed/tasks/inputdata.jsonl"
MAP_JSON = ROOT / "data/processed/maps/map2.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def namespace(original, output, java, javac):
    return argparse.Namespace(profile="full", map_path=original / "map2.txt", input_path=original / "inputdata.txt",
        canonical_input=CANONICAL, classes_dir=output / "classes", output_root=output,
        java=java, javac=javac, start_epoch=8260, max_epochs=90000, max_new_tasks=0,
        repeats=1, timeout_seconds=3600, speed_mps=2.0, storage_in_goal=47, storage_out_start=52,
        early_threshold_seconds=4800.0, storage_lead_seconds=2700.0, fault_schedule="none",
        cleanup_epoch_files=True, skip_compile=True, force=False, dry_run=False)


def prepare(original, output, java, javac):
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for source in sorted((original / "src").rglob("*.java")):
        relative = source.relative_to(original)
        mirror = ROOT / "legacy/jichang_origin_readonly" / relative
        normalized_equal = source.read_bytes().replace(b"\r\n", b"\n") == mirror.read_bytes().replace(b"\r\n", b"\n")
        records.append({"path": relative.as_posix(), "original_sha256": sha(source), "mirror_sha256": sha(mirror),
                        "bytes_equal": source.read_bytes() == mirror.read_bytes(), "normalized_equal": normalized_equal})
        if not normalized_equal:
            raise ValueError(f"Feng original source differs from audited repository mirror: {source}")
        frozen = output / "source" / relative
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, frozen)
    if len(records) != 15:
        raise ValueError("expected the 15-source original Feng project")
    input_comparison = []
    for name in ("map2.txt", "inputdata.txt"):
        left = original / name
        right = ROOT / "legacy/jichang_origin_readonly" / name
        normalized_equal = left.read_bytes().replace(b"\r\n", b"\n") == right.read_bytes().replace(b"\r\n", b"\n")
        input_comparison.append({"name": name, "original": evidence(left), "mirror": evidence(right),
                                 "bytes_equal": sha(left) == sha(right), "newline_normalized_equal": normalized_equal})
        if not normalized_equal:
            raise ValueError(f"original map2 input differs beyond line endings from repository mirror: {name}")
    _, raw = parse_legacy_tasks(original / "inputdata.txt")
    canonical = [json.loads(line) for line in CANONICAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    expanded = [row.to_dict() for row in expand_tasks(raw, 4800.0, 47, 52, 2700.0)]
    if expanded != canonical or len(raw) != 28506 or len(canonical) != 43603:
        raise ValueError("original raw map2 queue does not exactly reproduce the full canonical 1x workload")
    parsed = json.loads(json.dumps(parse_legacy_map(original / "map2.txt").to_dict()))
    saved = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    if {k: v for k, v in parsed.items() if k != "source_path"} != {k: v for k, v in saved.items() if k != "source_path"}:
        raise ValueError("original map2 file does not reproduce the protected canonical map")
    inputs = [original / "map2.txt", original / "inputdata.txt", MAP_JSON, CANONICAL,
              ROOT / "benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java", Path(runner.__file__), Path(__file__)]
    runner.LEGACY_ROOT = original
    manifest = {"schema": "g31.feng_alignment.original_java_map2.v1", "original_project": str(original),
                "source_comparison": records, "input_comparison": input_comparison,
                "algorithm": "native_original_java_hca", "map": "map2",
                "scope": "original complete map2 loaded queue; no unreachable-OD filtering; no empty-tray circulation; no edge-capacity addition",
                "raw_bags": len(raw), "segments": len(canonical), "map_nodes": len(saved["nodes"]), "map_edges": len(saved["edges"]),
                "speed_mps": 2.0, "start_epoch": 8260, "max_epochs": 90000, "end_epoch": 98259,
                "max_new_tasks": 0, "repeats": 1, "fault_schedule": "none", "storage_in_goal": 47, "storage_out_start": 52,
                "early_threshold_seconds": 4800.0, "storage_lead_seconds": 2700.0,
                "original_raw_expansion_exact_canonical": True, "original_map_exact_canonical_except_source_path": True,
                "inputs": [evidence(path) for path in inputs], "compile_command": runner.compile_command(javac, output / "classes"),
                "java": java, "javac": javac,
                "java_version": subprocess.run([java, "-version"], capture_output=True, text=True, check=True).stderr}
    write(output / "source_input_manifest.json", manifest)
    for path in inputs[2:]:
        frozen = output / "source" / path.relative_to(ROOT)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, frozen)
    started = time.perf_counter()
    runner.compile_java(javac, output / "classes")
    write(output / "compile_receipt.json", {"wall_seconds": time.perf_counter() - started,
        "classes": [{"path": str(path.relative_to(output / "classes")), "sha256": sha(path)} for path in sorted((output / "classes").rglob("*.class"))]})
    command = runner.java_run_command(java=java, classes_dir=output / "classes", map_path=original / "map2.txt",
        input_path=original / "inputdata.txt", start_epoch=8260, max_epochs=90000, max_new_tasks=0,
        run_dir=output / "run_01", fault_schedule="none", speed_mps=2.0,
        storage_in_goal=47, storage_out_start=52, early_threshold_seconds=4800.0, storage_lead_seconds=2700.0)
    write(output / "prepared_command.json", {"cwd": str(output / "run_01"), "command": command, "argv_prepare": sys.argv})
    print(json.dumps({"status": "prepared_and_compiled", "output": str(output), "nodes": len(saved["nodes"]), "edges": len(saved["edges"]),
                      "raw_bags": len(raw), "segments": len(canonical), "canonical_sha256": sha(CANONICAL)}))


def run(output):
    manifest = json.loads((output / "source_input_manifest.json").read_text(encoding="utf-8"))
    original = Path(manifest["original_project"])
    for record in manifest["inputs"]:
        if sha(record["path"]) != record["sha256"]:
            raise ValueError(f"prepared input changed before run: {record['path']}")
    for record in manifest["source_comparison"]:
        if sha(original / record["path"]) != record["original_sha256"]:
            raise ValueError("original Java source changed after compilation")
    receipt = json.loads((output / "compile_receipt.json").read_text(encoding="utf-8"))
    for record in receipt["classes"]:
        if sha(output / "classes" / record["path"]) != record["sha256"]:
            raise ValueError("compiled Java class changed after preparation")
    runner.LEGACY_ROOT = original
    return runner.run_campaign(namespace(original, output, manifest["java"], manifest["javac"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--original-project", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--java", default=shutil.which("java"))
    parser.add_argument("--javac", default=shutil.which("javac"))
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.java or not args.javac:
            raise ValueError("java and javac are required")
        prepare(args.original_project.resolve(strict=True), args.output.resolve(), args.java, args.javac)
        return 0
    return run(args.output.resolve(strict=True))


if __name__ == "__main__":
    raise SystemExit(main())
