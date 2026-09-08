"""Build the isolated new native module without touching the retained b00 build."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/g31_fault_potential_repair_20260907"
CMAKE = r"C:\Program Files\CMake\bin\cmake.exe"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    # MSBuild's case-insensitive environment rejects inherited PATH + Path.
    # Python reconstructs one key per spelling; do not change machine settings.
    environment = {key.upper(): value for key, value in os.environ.items()}
    if mode == "configure":
        command = [CMAKE, "--fresh", "-S", str(ROOT), "-B", str(BUILD), "-G", "Visual Studio 17 2022", "-A", "x64",
                   "-DCZR005_BUILD_PYBIND=ON", "-DPython3_EXECUTABLE=C:/PROGRAMING/python3.11.9/python.exe",
                   "-Dpybind11_DIR=C:/PROGRAMING/python3.11.9/Lib/site-packages/pybind11/share/cmake/pybind11"]
    elif mode == "build":
        targets = sys.argv[2:] or ["czr005_cpp", "test_g31_advertised_fault_reset"]
        command = [CMAKE, "--build", str(BUILD), "--config", "Release", "--target", *targets, "--parallel", "2"]
    else:
        raise ValueError("configure or build")
    result = subprocess.run(command, cwd=ROOT, env=environment)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
