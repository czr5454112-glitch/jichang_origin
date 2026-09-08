"""Bounded native tests for V3's implemented speed / known-all-day-fault scope."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmarks/java/hca_paper_suite_v3"
PARENT = ROOT / "benchmarks/java/hca_time_label_repair_v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def identity(paths: list[Path], base: Path) -> dict:
    files = {p.relative_to(base).as_posix(): sha(p) for p in sorted(paths)}
    content = "".join(name + "\0" + digest + "\n" for name, digest in files.items()).encode()
    return {"algorithm": "SHA256(sorted relative path + NUL + file SHA256 + newline)",
            "sha256": hashlib.sha256(content).hexdigest(), "files": files}


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def fixture(path: Path) -> None:
    # Source0 -> junction1 -> goal3 is 20m + 1s; alternative via2 is30m +1s.
    # Source4 -> goal3 is a separate storage-out lane, allowing independent EBS legs.
    lines = ["5 1 0 4", "0 1 0 0 0 1 2", "1 4 1 0 10 3", "2 4 1 10 10 3",
             "3 2 0 0 20", "4 1 0 20 0 3"]
    lines += ["0 10 15 20 1000", "1000 0 1000 10 1000", "1000 1000 0 15 1000",
              "1000 1000 1000 0 1000", "1000 1000 1000 5 0"]
    lines += ["0 1 10 2.5", "1 3 10 2.5", "0 2 15 2.5", "2 3 15 2.5", "4 3 5 2.5"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", default=shutil.which("java"))
    parser.add_argument("--javac", default=shutil.which("javac"))
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/runtime/hca_paper_suite_v3_20260907/preflight")
    parser.add_argument("--build", type=Path, default=ROOT / "build/hca_paper_suite_v3_microtests")
    args = parser.parse_args()
    base, build = args.output.resolve(), args.build.resolve()
    assert not (base / "microtests.json").exists(), "choose a fresh immutable output directory"
    originals = sorted(PARENT.rglob("*.java"))
    original_identity = identity(originals, PARENT)
    core = sorted((SOURCE / "App").glob("*.java")) + [SOURCE / "ICS_GUI/ICS_GUI.java"]
    assert len(core) == 10
    for item in core:
        assert item.read_bytes() == (PARENT / item.relative_to(SOURCE)).read_bytes()
    versions = {}
    for key, folder, wrapper in (("v2", PARENT, "HcaSegmentIdentityBenchmark"),
                                 ("v3", SOURCE, "HcaPaperSuiteBenchmark")):
        classes = build / key
        classes.mkdir(parents=True, exist_ok=True)
        sources = sorted(folder.rglob("*.java"))
        command = [args.javac, "-encoding", "UTF-8", "-d", str(classes), *map(str, sources)]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        versions[key] = {"classes": str(classes), "compile_command": command,
                         "compile_stderr": completed.stderr, "source": identity(sources, folder),
                         "class": identity(list(classes.rglob("*.class")), classes)}
    cases = []

    def run(name: str, *, version: str = "v3", speed: float = 2.5,
            mode: str = "BASELINE", bias: float = 0, schedule: str = "none",
            error: str | None = None, lines: list[str] | None = None,
            threshold: float = 1000, epochs: int = 40) -> dict:
        target = base / "native" / name
        assert not target.exists(), "fixture output already exists"
        target.mkdir(parents=True)
        fixture(target / "map.txt")
        (target / "input.txt").write_text("ID EntryTime STD star end Unloader Loader\n" +
            "\n".join(lines or ["7 100 120 0 3 2 10"]) + "\n", encoding="utf-8", newline="\n")
        command = [args.java, "-Xmx256m", "-cp", versions[version]["classes"],
                   "HcaPaperSuiteBenchmark" if version == "v3" else "HcaSegmentIdentityBenchmark",
                   str(target / "map.txt"), str(target / "input.txt"), "100", str(epochs), "0", "1", "0",
                   str(target / "routes.csv"), str(target / "summary.csv"), schedule, "0", "0",
                   str(target / "release.csv"), str(speed), "3", "4", str(threshold), "5",
                   str(target / "segment_execution_identity.csv"), str(target / "execution_terminal.csv")]
        if version == "v3":
            command += [mode, str(bias), "104729", str(target / "suite_audit.csv")]
        done = subprocess.run(command, cwd=target, capture_output=True, text=True, timeout=30)
        (target / "stdout.txt").write_text(done.stdout, encoding="utf-8")
        (target / "stderr.txt").write_text(done.stderr, encoding="utf-8")
        assert (done.returncode == 0) if error is None else (done.returncode != 0 and error in done.stderr), done.stderr
        item = {"name": name, "directory": str(target), "command": command,
                "returncode": done.returncode, "expected_error": error, "status": "PASS"}
        if error is None:
            item["summary"] = records(target / "summary.csv")[0]
            item["terminal"] = records(target / "execution_terminal.csv")
            item["routes"] = records(target / "routes.csv")
            assert int(item["summary"]["terminal_accounting_residual"]) == 0
        cases.append(item)
        return item

    parent = run("v2_control", version="v2")
    current = run("v3_control")
    equality = {}
    for name in ("routes.csv", "release.csv", "output.txt", "outputstarttime.txt",
                 "segment_execution_identity.csv", "execution_terminal.csv"):
        a, b = Path(parent["directory"]) / name, Path(current["directory"]) / name
        assert a.read_bytes() == b.read_bytes(), name
        equality[name] = sha(a)
    for field, value in parent["summary"].items():
        if field != "method":
            assert value == current["summary"][field], field
    assert current["routes"][0]["path"] == "0;1;3"
    checks = [{"name": "V2_no_fault_scientific_bytes_unchanged_except_method", "status": "PASS", "files": equality}]
    for speed in (1.5, 2.0, 2.5, 3.0):
        value = current if speed == 2.5 else run("speed_" + str(speed).replace(".", "p"), speed=speed)
        route = value["routes"][0]
        expected = float(route["epoch"]) + 20 / speed + 1
        assert abs(float(route["finish_time"]) - expected) < 1e-8
        assert route["path"] == "0;1;3"
        checks.append({"name": "real_edge_speed_" + str(speed), "status": "PASS", "expected_finish": expected})
    detour = run("all_day_detour", mode="FULL_DAY_KNOWN_EDGE_FAILURE", schedule="100:0:1:fault")
    assert detour["routes"][0]["path"] == "0;2;3"
    assert detour["terminal"][0]["terminal_state"] == "COMPLETED"
    assert int(detour["summary"]["active_fault_count"]) == 1
    blocked = run("all_day_unreachable", mode="FULL_DAY_KNOWN_EDGE_FAILURE",
                  schedule="100:0:1:fault;100:0:2:fault", lines=["7 100 120 0 3 2 10", "8 101 120 0 3 2 10"])
    assert {item["terminal_state"] for item in blocked["terminal"]} == {"UNPLANNED", "NOT_RELEASED"}
    assert blocked["routes"] == []
    checks.append({"name": "known_fault_real_detour_and_unreachable_population_preserved", "status": "PASS"})
    overlap = run("EBS_overlap", lines=["7 100 106 0 3 2 10"], threshold=5)
    legs = {item["leg"]: item for item in overlap["terminal"]}
    assert len(legs) == 2 and all(item["terminal_state"] == "COMPLETED" for item in legs.values())
    assert float(legs["storage_out"]["completion_epoch"]) < float(legs["storage_in"]["completion_epoch"])
    checks.append({"name": "EBS_unique_execution_and_no_added_precedence", "status": "PASS"})
    for name, keywords, message in [
        ("reject_dynamic", {"mode": "DYNAMIC"}, "real dynamic/LRA execution is not implemented"),
        ("reject_static_lra", {"mode": "STATIC_LRA"}, "real dynamic/LRA execution is not implemented"),
        ("reject_bias", {"bias": .1}, "nonzero physical speed bias is not implemented"),
        ("reject_late_fault", {"mode": "FULL_DAY_KNOWN_EDGE_FAILURE", "schedule": "101:0:1:fault"}, "must start at startEpoch"),
        ("reject_repair", {"mode": "FULL_DAY_KNOWN_EDGE_FAILURE", "schedule": "100:0:1:repair"}, "never repair"),
        ("reject_unknown_edge", {"mode": "FULL_DAY_KNOWN_EDGE_FAILURE", "schedule": "100:3:0:fault"}, "unknown scheduled edge"),
        ("reject_duplicate_fault", {"mode": "FULL_DAY_KNOWN_EDGE_FAILURE", "schedule": "100:0:1:fault;100:0:1:fault"}, "duplicate directed failed edge")]:
        run(name, error=message, **keywords)
        checks.append({"name": name, "status": "PASS"})
    assert identity(originals, PARENT) == original_identity, "frozen V2 source changed"
    for key in versions:
        classes = Path(versions[key]["classes"])
        assert versions[key]["class"] == identity(list(classes.rglob("*.class")), classes)
    for case in cases:
        target = Path(case["directory"])
        case["native_files"] = identity([p for p in target.rglob("*") if p.is_file()], target)
    result = {"schema": "czr005.hca_paper_suite_v3_microtests.v1", "status": "PASS",
              "check_count": len(checks), "checks": checks, "cases": cases, "builds": versions,
              "test_driver_sha256": sha(Path(__file__)), "original_v2_unchanged": True,
              "formal_population_simulations_executed": 0,
              "dynamic_and_LRA_implementation_status": "NOT_IMPLEMENTED_EXPLICITLY_REJECTED"}
    write(base / "microtests.json", result)
    print(json.dumps({"status": "PASS", "checks": len(checks), "cases": len(cases), "output": str(base / "microtests.json"),
                      "source_sha256": versions["v3"]["source"]["sha256"], "class_sha256": versions["v3"]["class"]["sha256"]}))


if __name__ == "__main__":
    main()
