"""Build a new diagnostic binary only; deliberately never run CTest/NativeSession."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pybind11

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--background-log", type=Path, required=True)
    parser.add_argument("--vcvars", type=Path, required=True)
    parser.add_argument("--ninja", type=Path, required=True)
    args = parser.parse_args()
    build, output = args.build_dir.resolve(), args.receipt_dir.resolve()
    if not build.is_relative_to(ROOT) or build.name != "build_lt_session_026":
        raise ValueError("native_timing_build:unexpected_build_target")
    # Refuse even an existing empty target so no prior build can be overwritten.
    build.mkdir(exist_ok=False)
    output.mkdir(parents=True, exist_ok=False)
    source_files = lambda: sorted([ROOT/"CMakeLists.txt", *ROOT.glob("cpp/**/*.hpp"), *ROOT.glob("cpp/**/*.cpp")])
    snapshot = lambda: {str(p.relative_to(ROOT)): sha(p) for p in source_files()}
    before = snapshot()
    for relative, digest in before.items():
        target = output/"source"/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
        if sha(target) != digest:
            raise ValueError("native_timing_build:archive_changed:" + relative)
    shutil.copyfile(__file__, output/"build_native_observation_indices.py")
    cmake = shutil.which("cmake")
    if not cmake:
        raise RuntimeError("cmake unavailable")
    configure = [cmake, "-S", str(ROOT), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_TRY_COMPILE_CONFIGURATION=Release", "-DCZR005_BUILD_PYBIND=ON",
        f"-DPython3_EXECUTABLE={sys.executable}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}",
        "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={args.ninja.resolve()}"]
    commands = [configure, [cmake, "--build", str(build), "--clean-first", "--parallel", "1",
        "--target", "czr005_circulation", "test_circulation_runtime"]]
    receipt = {"schema": "g31.circulation.build_only.v1", "status": "started",
        "source_before": before, "source_root": str(ROOT), "build_root": str(build),
        "commands": [], "requested_commands": commands, "parallel_jobs": 1,
        "ctest_executed": False, "native_session_executed": False,
        "native_acceptance": "held_pending_parent_release", "python": sys.executable}
    def save():
        (output/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    def background(event, **fields):
        record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "event": event,
            "work": "Native026 configure/compile only, parallel 1; no CTest or circulation simulation",
            "receipt": str(output/"receipt.json"), "existing_native_policy_or_binary_modified": False,
            "timing_scope": "Concurrent single-job compilation is disclosed; overlapping wall-time measurements are not isolated.", **fields}
        with args.background_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record)+"\n")
    save()
    started = time.perf_counter()
    background("native026_build_started", requested_commands=commands)
    try:
        for index, command in enumerate(commands):
            script = output/f"command_{index:02d}.cmd"
            script.write_text('@echo off\ncall "' + str(args.vcvars.resolve()) + '"\n'
                'if errorlevel 1 exit /b %errorlevel%\nset VSLANG=1033\n'
                + subprocess.list2cmdline(command) + '\nexit /b %errorlevel%\n', encoding="utf-8")
            command_started = time.perf_counter()
            with (output/f"command_{index:02d}.stdout.log").open("wb") as stdout, (output/f"command_{index:02d}.stderr.log").open("wb") as stderr:
                process = subprocess.run(["cmd.exe", "/d", "/c", str(script)], cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
            receipt["commands"].append({"argv": command, "exit_code": process.returncode,
                "wall_seconds": time.perf_counter()-command_started})
            save()
            if process.returncode:
                raise RuntimeError(f"native_timing_build:command_{index}_exit_{process.returncode}")
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = [path for path in set(before) | set(receipt["source_after"])
            if before.get(path) != receipt["source_after"].get(path)]
        if receipt["source_changed"]:
            raise RuntimeError("native_timing_build:source_changed")
        binaries = [*build.glob("python/czr005_circulation*.pyd"), *build.glob("test_circulation_runtime*.exe")]
        receipt["binary_sha256"] = {str(path): sha(path) for path in binaries}
        if len(binaries) != 2:
            raise RuntimeError("native_timing_build:missing_outputs")
        receipt["status"] = "build_passed_tests_held"
    except Exception as error:
        receipt["status"], receipt["error"] = "failed", str(error)
    receipt["wall_seconds"] = time.perf_counter()-started
    save()
    background("native026_build_finished", status=receipt["status"], elapsed_seconds=receipt["wall_seconds"],
        commands=receipt["commands"], binary_sha256=receipt.get("binary_sha256", {}),
        source_changed=receipt.get("source_changed"), error=receipt.get("error"))
    print(json.dumps({key: receipt[key] for key in ("status", "wall_seconds")}, indent=2))
    return 0 if receipt["status"] == "build_passed_tests_held" else 1


if __name__ == "__main__":
    raise SystemExit(main())
