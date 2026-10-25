"""Compile an immutable snapshot of the standalone no-wait candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.name.replace("_", "").isalnum():
        raise ValueError("build name must be letters, digits and underscores")
    build = ROOT / "build" / ("g31_no_wait_" + args.name)
    if build.exists():
        raise FileExistsError(build)
    frozen = build / "source"
    frozen.mkdir(parents=True)
    for filename in ("core.cpp", "CMakeLists.txt", "build.py"):
        shutil.copyfile(Path(__file__).with_name(filename), frozen / filename)
    receipt = {"status": "building", "source_sha256": {p.name: sha(p) for p in frozen.iterdir()},
               "python": sys.executable, "python_version": sys.version}
    receipt_path = build / "build_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    pybind = Path(sys.executable).parent / "Lib/site-packages/pybind11/share/cmake/pybind11"
    commands = [
        "@echo off",
        'call "C:\\PROGRAMING\\visual studio\\Visual studio\\VC\\Auxiliary\\Build\\vcvars64.bat"',
        "if errorlevel 1 exit /b %errorlevel%",
        f'"C:\\Program Files\\CMake\\bin\\cmake.exe" -S "{frozen}" -B "{build}" -G Ninja '
        '-DCMAKE_MAKE_PROGRAM="C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe" '
        f'-Dpybind11_DIR="{pybind}" -DPython_EXECUTABLE="{sys.executable}" '
        '-DCMAKE_BUILD_TYPE=Release -DCMAKE_TRY_COMPILE_CONFIGURATION=Release '
        '-DCMAKE_CXX_FLAGS_DEBUG="/Z7 /Ob0 /Od /RTC1"',
        "if errorlevel 1 exit /b %errorlevel%",
        f'"C:\\Program Files\\CMake\\bin\\cmake.exe" --build "{build}" --config Release --parallel 2',
        "exit /b %errorlevel%",
    ]
    batch = build / "build.cmd"
    batch.write_text("\n".join(commands) + "\n", encoding="ascii")
    with (build / "build.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run(["cmd.exe", "/d", "/c", str(batch)], stdout=stream, stderr=subprocess.STDOUT)
    outputs = list((build / "python").glob("g31_nowait*.pyd"))
    receipt.update(status="complete" if result.returncode == 0 and len(outputs)==1 else "failed",
                   returncode=result.returncode,
                   binaries={str(p): sha(p) for p in outputs})
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)
    if receipt["status"] != "complete":
        raise RuntimeError(f"build failed; inspect {build / 'build.log'}")


if __name__ == "__main__":
    main()
