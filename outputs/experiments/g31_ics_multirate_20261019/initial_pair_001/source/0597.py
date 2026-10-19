"""Compile and execute native checkpoint regressions with immutable receipts.

This Windows development-machine runner invokes actual MSVC compilation for
each target; it does not trust incremental header dependency scanning. CMake's
circulation_checkpoint target remains the portable test entry point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).absolute().parents[3]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vcvars", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", choices=("test_circulation_checkpoint", "test_circulation_runtime",
                        "test_g4irsf14_state_clone_protocol"),
                        default=["test_circulation_checkpoint", "test_circulation_runtime", "test_g4irsf14_state_clone_protocol"])
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    build = ROOT / "build_lt_checkpoint" / out.name
    build.mkdir(parents=True, exist_ok=False)
    # These paths enter a generated cmd file. Permit ordinary Windows paths,
    # never shell metacharacters or cmd environment substitution.
    for value in (ROOT, out, build, args.vcvars):
        if any(char in str(value) for char in '\r\n"&|<>^%'):
            raise ValueError("unsupported shell metacharacter in build path")
    targets = tuple(args.targets)
    # Header-only runtime plus these exact translation units. The concurrently
    # developed Python binding translation unit is not a compiled input here.
    sources = sorted([*(p for p in ROOT.glob("cpp/ics_core/**/*.hpp")
                        if "bindings" not in p.relative_to(ROOT).parts),
                      *(ROOT / "cpp/tests" / (name + ".cpp") for name in targets)])
    snapshot = lambda: {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}
    receipt = {"schema": "g31.circulation.native_checkpoint_validation.v1", "status": "started",
               "source_root": str(ROOT), "build_root": str(build), "source_before": snapshot(),
               "commands": [], "binary_sha256": {}, "incremental_build_used": False}
    start = time.perf_counter()
    try:
        for target in targets:
            executable = build / (target + ".exe")
            script = out / (target + ".cmd")
            # The literal escaped quotes are required by cl's /D parser; they
            # define a C++ string and are not JSON/shell interpolation.
            script.write_text(
                '@echo off\ncall "' + str(args.vcvars.absolute()) + '"\n'
                'if errorlevel 1 exit /b %errorlevel%\n'
                'cl /nologo /std:c++17 /EHsc /O2 /MD /bigobj /DCZR005_EVENT_RUNTIME_TESTING=1 '
                '/DCZR005_SOURCE_DIR=\\"' + ROOT.as_posix() + '\\" '
                '/I"' + (ROOT / 'cpp').as_posix() + '" "' +
                (ROOT / 'cpp/tests' / (target + '.cpp')).as_posix() + '" '
                '/Fo"' + (build / (target + '.obj')).as_posix() + '" '
                '/Fe"' + executable.as_posix() + '"\nexit /b %errorlevel%\n', encoding="utf-8")
            for phase, argv in (("compile", ["cmd.exe", "/c", str(script)]),
                                ("run", [str(executable)])):
                with (out / f"{target}.{phase}.stdout.log").open("wb") as stdout, \
                     (out / f"{target}.{phase}.stderr.log").open("wb") as stderr:
                    started = time.perf_counter()
                    result = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
                receipt["commands"].append({"target": target, "phase": phase, "argv": argv,
                                            "exit_code": result.returncode,
                                            "wall_seconds": time.perf_counter()-started})
                if result.returncode:
                    raise RuntimeError(f"{target} {phase} failed: {result.returncode}; raw logs preserved")
            receipt["binary_sha256"][str(executable)] = digest(executable)
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = [p for p, h in receipt["source_before"].items()
                                     if receipt["source_after"].get(p) != h]
        if receipt["source_changed"]:
            raise RuntimeError("sources changed during validation; development evidence only")
        receipt["status"] = "passed"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = str(exc)
    receipt["wall_seconds"] = time.perf_counter()-start
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "wall_seconds")}, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
