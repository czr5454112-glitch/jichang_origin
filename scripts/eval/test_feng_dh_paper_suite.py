"""Production-linked physical checks and V5 equivalence before formal V6 runs."""
from pathlib import Path
import csv
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_dh_paper_suite as suite
from scripts.eval import run_feng_dh_v5_campaign as old

OUT = ROOT / "outputs/runtime/feng_dh_paper_suite_v6_20260907/preflight/production"


def run(command, output):
    value = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    Path(output).write_text(value.stdout + value.stderr, encoding="utf-8")
    suite.require(value.returncode == 0, f"preflight failed: {command}; {value.stderr}")
    return value.stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    build = suite.compile_build()
    old.compiled_identity(old.CLASSES)
    harness = OUT / "harness"
    harness.mkdir(exist_ok=True)
    sources = [ROOT / "tests/java/App" / name for name in
               ("BoundaryClearanceAudit.java", "FengDhSuiteSpeedAudit.java", "FengDhSuiteFaultAudit.java")]
    run([suite.JAVAC, "-encoding", "UTF-8", "-cp", str(suite.BUILD), "-d", str(harness), *map(str, sources)],
        OUT / "compile_harness.txt")
    classpath = str(harness) + ";" + str(suite.BUILD)
    rows = []
    for name, args in (("BoundaryClearanceAudit", [str(OUT / "boundary")]),
                       ("FengDhSuiteSpeedAudit", [str(ROOT / "legacy/jichang_origin_readonly/map2.txt"),
                                                  str(ROOT / "data/processed/maps/nanning_legacy.txt")]),
                       ("FengDhSuiteFaultAudit", [])):
        stdout = run([suite.JAVA, "-cp", classpath, "App."+name, *args], OUT / (name+".jsonl"))
        rows += [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    for map_name in ("map2", "nanning"):
        identity = suite.read(ROOT / f"data/processed/workloads/cie_external_robustness/{map_name}_1p00x/seed_104729/identity.json")
        raw = OUT / (map_name + "_first_200.txt")
        raw.write_text("\n".join(Path(identity["raw_path"]).read_text(encoding="utf-8").splitlines()[:201])+"\n",
                       encoding="utf-8")
        dirs = []
        for label, classes in (("old_v5", old.CLASSES), ("new_v6", suite.BUILD)):
            output = OUT / (map_name+"_"+label)
            suite.require(not output.exists(), "never overwrite a prior preflight simulation")
            args = [suite.JAVA, "-Xmx768m", "-cp", str(classes), "App.FengDhBenchmark", "run",
                    "--map", identity["map_path"], "--input", str(raw), "--output", str(output),
                    "--horizon-seconds", "98259", "--storage-in-goal", str(identity["storage_in_goal"]),
                    "--storage-out-start", str(identity["storage_out_start"])]
            run(args, OUT / (map_name+"_"+label+".stdout.txt"))
            dirs.append(output)
        for name in ("bags.csv", "segments.csv", "event_summary.csv", "trace.csv"):
            a, b = (suite.csv_rows(directory / name) for directory in dirs)
            suite.require(len(a) == len(b), "V5/V6 row-count drift")
            for left, right in zip(a, b):
                suite.require(left == {key: right[key] for key in left}, f"2.5 physical V5/V6 mismatch: {map_name}/{name}")
        rows.append({"test": "V5_2p5_real_map_200_raw_bags_equivalence", "map": map_name, "pass": True})
    suite.require(all(row["pass"] for row in rows), "failed mechanism gate")
    result = {"status": "PASS", "case_count": len(rows), "cases": rows,
              "build_identity_sha256": suite.sha(suite.BUILD / "build_identity.json"), "production_build": build,
              "legacy_v5_preserved": old.check_source()["source_files"],
              "old_embedded_microtests_note": "V5 retains three stale pre-boundary-clearance expectations. They are not used as V6 gates; the dedicated nine BC assertions above apply to the V5 semantics."}
    suite.write(OUT / "preflight.json", result)
    print(json.dumps({"status": "PASS", "case_count": len(rows)}))


if __name__ == "__main__":
    main()
