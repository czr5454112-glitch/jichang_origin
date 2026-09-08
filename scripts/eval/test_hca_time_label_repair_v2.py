"""Bounded real-Java regression checks for the isolated two-assignment repair."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COPY = ROOT / "benchmarks/java/hca_time_label_repair_v2"
ORIGINAL = ROOT / "legacy/jichang_origin_readonly/src"
AUDIT = ROOT / "tests/java/hca_time_label_repair_v2/HcaTimeLabelAudit.java"
WRAPPER = ROOT / "benchmarks/java/HcaSegmentIdentityBenchmark.java"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(directory: Path) -> list[Path]:
    return sorted((directory / "App").glob("*.java")) + [directory / "ICS_GUI/ICS_GUI.java"]


def manifest(paths: list[Path], base: Path) -> dict:
    rows = [{"path": p.relative_to(base).as_posix(), "sha256": sha(p), "size_bytes": p.stat().st_size}
            for p in sorted(paths)]
    digest = hashlib.sha256("".join(r["path"] + "\0" + r["sha256"] + "\n" for r in rows).encode()).hexdigest()
    return {"algorithm": "SHA256(sorted relative path + NUL + file SHA256 + newline)",
            "manifest_sha256": digest, "files": rows}


def normalized(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--java", default=shutil.which("java"))
    parser.add_argument("--javac", default=shutil.which("javac"))
    parser.add_argument("--map2", type=Path, default=ROOT / "legacy/jichang_origin_readonly/map2.txt")
    parser.add_argument("--nanning-map", type=Path, default=ROOT / "data/processed/maps/nanning_legacy.txt")
    parser.add_argument("--build-root", type=Path, default=ROOT / "build/hca_time_label_repair_v2_microtests")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/runtime/hca_time_label_repair_v2_20260906/preflight/microtests.json")
    args = parser.parse_args()
    assert args.java and args.javac, "JDK required"
    assert len(sources(COPY)) == len(sources(ORIGINAL)) == 10
    original_before = manifest(sources(ORIGINAL) + [WRAPPER], ROOT)
    source_before = manifest(sources(COPY), ROOT)
    insertion = b"\t\t\t\t\t    n.t1=t1;\n\t\t\t\t\t    n.t2=t2;\n"
    for reference in sources(ORIGINAL):
        candidate = COPY / reference.relative_to(ORIGINAL)
        body = normalized(candidate)
        if reference.name == "Astar.java":
            assert body.count(insertion) == 1, "repair must add exactly two assignments"
            body = body.replace(insertion, b"")
        assert body == normalized(reference), f"unapproved algorithm change: {candidate}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    runs = {}
    for mode, directory in (("original", ORIGINAL), ("repaired", COPY)):
        classes = args.build_root.resolve() / mode
        classes.mkdir(parents=True, exist_ok=True)
        compile_command = [args.javac, "-encoding", "UTF-8", "-d", str(classes),
                           *map(str, sources(directory)), str(AUDIT)]
        compiled = subprocess.run(compile_command, cwd=ROOT, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=90)
        (args.output.parent / f"{mode}_compile_stderr.txt").write_text(compiled.stderr, encoding="utf-8")
        assert compiled.returncode == 0, compiled.stderr
        command = [args.java, "-Djava.awt.headless=true", "-cp", str(classes), "App.HcaTimeLabelAudit",
                   mode, str(args.map2.resolve()), str(args.nanning_map.resolve())]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="strict", timeout=30)
        (args.output.parent / f"{mode}_microtests.jsonl").write_text(result.stdout, encoding="utf-8")
        (args.output.parent / f"{mode}_microtests.stderr.txt").write_text(result.stderr, encoding="utf-8")
        assert result.returncode == 0, result.stderr
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        assert records[-1]["status"] == "PASS" and records[-1]["asserted_checks"] == 7
        runs[mode] = {"compile_command": compile_command, "command": command,
                      "records": records, "core_classes": manifest(
                          [p for p in classes.rglob("*.class") if not p.name.startswith("HcaTimeLabelAudit")], classes)}
    def case(mode: str, name: str) -> dict:
        return next(r for r in runs[mode]["records"] if r.get("case") == name)
    assert case("original", "map2_5_to_47_control") == case("repaired", "map2_5_to_47_control")
    assert case("original", "rejected_earlier_candidate") == case("repaired", "rejected_earlier_candidate")
    assert manifest(sources(ORIGINAL) + [WRAPPER], ROOT) == original_before, "original or wrapper changed"
    assert manifest(sources(COPY), ROOT) == source_before, "variant source changed during tests"
    payload = {"schema": "czr005.hca_time_label_repair_v2.microtests.v1", "status": "PASS",
               "variant": "HCA_TIME_LABEL_REPAIR_V2", "production_code_change": ["n.t1=t1;", "n.t2=t2;"],
               "java_checks_per_variant": 7, "java_checks_total": 14,
               "cross_variant_checks": ["unchanged map2 path and t1/t2", "rejected candidate unchanged"],
               "source_scope_checks": ["only two assignments differ after newline normalization",
                                       "original and frozen wrapper bytes unchanged", "variant bytes unchanged during tests"],
               "full_simulation_executed": False,
               "interpretation": "Original mode PASS means expected defects reproduced; original five-node/Nanning formula_valid remain false. Repaired mode requires valid recurrences and reservation behavior.",
               "driver_sha256": sha(Path(__file__)), "test_source_sha256": sha(AUDIT),
               "sources": source_before, "original_and_wrapper": original_before,
               "maps": [{"path": str(p.resolve()), "sha256": sha(p)} for p in (args.map2, args.nanning_map)],
               "runs": runs}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "java_assertions": 14, "output": str(args.output),
                      "source_manifest_sha256": source_before["manifest_sha256"]}))


if __name__ == "__main__":
    main()
