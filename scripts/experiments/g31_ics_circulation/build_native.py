"""Clean native build with source/binary identity and raw command receipts.

The MSVC environment can be supplied using --vcvars. A clean rebuild is
intentional: localized /showIncludes output must not silently reuse old headers.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).absolute().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build_g31_circulation")
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--vcvars", type=Path)
    parser.add_argument("--ninja", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    build = args.build_dir.absolute()
    receipt_dir = args.receipt_dir.absolute()
    receipt_dir.mkdir(parents=True, exist_ok=False)
    build.mkdir(parents=True, exist_ok=True)
    source_files = sorted([ROOT / "CMakeLists.txt", *ROOT.glob("cpp/**/*.hpp"), *ROOT.glob("cpp/**/*.cpp")])
    snapshot = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    receipt = {"schema": "g31.circulation.clean_build.v1", "source_before": snapshot(),
               "commands": [], "status": "started", "clean_first": True,
               "source_root": str(ROOT), "build_root": str(build), "python": sys.executable}
    pybind11 = importlib.import_module("pybind11")
    cmake = shutil.which("cmake")
    if not cmake:
        raise RuntimeError("cmake unavailable")
    configure = [cmake, "-S", str(ROOT), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                 "-DCMAKE_TRY_COMPILE_CONFIGURATION=Release", "-DCZR005_BUILD_PYBIND=ON",
                 f"-DPython3_EXECUTABLE={sys.executable}", f"-Dpybind11_DIR={pybind11.get_cmake_dir()}"]
    if args.ninja:
        configure += ["-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={args.ninja.absolute()}"]
    commands = [configure, [cmake, "--build", str(build), "--clean-first", "--parallel", str(args.jobs),
                           "--target", "czr005_circulation", "test_circulation_runtime"],
                [shutil.which("ctest") or "ctest", "--test-dir", str(build), "--output-on-failure",
                 "-R", "^circulation_runtime$", "--output-junit", str(receipt_dir / "native_junit.xml")]]
    start = time.perf_counter()
    try:
        for i, command in enumerate(commands):
            executable = command
            if args.vcvars:
                if os.name != "nt":
                    raise ValueError("--vcvars requires Windows")
                # Arguments are paths/tool switches, never user-authored script bodies.
                # Keep the environment and build in one cmd process; no file deletion.
                script = receipt_dir / f"command_{i:02d}.cmd"
                script.write_text('@echo off\ncall "' + str(args.vcvars.absolute()) + '"\n'
                                  'if errorlevel 1 exit /b %errorlevel%\nset VSLANG=1033\n'
                                  + subprocess.list2cmdline(command) + '\nexit /b %errorlevel%\n', encoding="utf-8")
                executable = ["cmd.exe", "/c", str(script)]
            with (receipt_dir / f"command_{i:02d}.stdout.log").open("wb") as stdout, \
                 (receipt_dir / f"command_{i:02d}.stderr.log").open("wb") as stderr:
                t = time.perf_counter()
                process = subprocess.run(executable, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
            receipt["commands"].append({"argv": command, "actual_argv": executable,
                                        "exit_code": process.returncode, "wall_seconds": time.perf_counter()-t})
            if process.returncode:
                raise RuntimeError(f"command {i} failed with exit {process.returncode}; raw logs preserved")
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = [p for p, h in receipt["source_before"].items() if receipt["source_after"].get(p) != h]
        if receipt["source_changed"]:
            raise RuntimeError("C++ source changed during the build; result not frozen")
        binaries = sorted([*build.glob("python/czr005_circulation*.pyd"), *build.glob("python/czr005_circulation*.so"),
                           *build.glob("test_circulation_runtime*exe")])
        receipt["binary_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries if p.is_file()}
        if not receipt["binary_sha256"]:
            raise RuntimeError("no built binary found")
        receipt["status"] = "passed"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = str(exc)
    receipt["wall_seconds"] = time.perf_counter()-start
    (receipt_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "wall_seconds")}, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
