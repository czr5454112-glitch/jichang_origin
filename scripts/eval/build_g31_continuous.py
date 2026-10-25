"""Build an immutable snapshot of the registered continuous-motion G31 engine."""
from __future__ import annotations
import argparse
import hashlib
import importlib.machinery
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def build(name, *, generator=None):
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("build name must contain letters, digits or underscores")
    output = ROOT / "build" / ("g31_continuous_" + name)
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    source.mkdir()
    for filename in ("core.cpp", "CMakeLists.txt"):
        shutil.copyfile(ROOT / "cpp/ics_core/continuous_motion" / filename, source / filename)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    receipt = dict(status="building", source_sha256={p.name:digest(p) for p in source.iterdir()},
                   python=sys.executable, python_version=sys.version)
    receipt_path = output / "build_receipt.json"
    def save(): receipt_path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    save()
    try:
        import pybind11
        configure = ["cmake", "-S", str(source), "-B", str(output),
                     "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_TRY_COMPILE_CONFIGURATION=Release",
                     "-Dpybind11_DIR="+pybind11.get_cmake_dir(), "-DPython_EXECUTABLE="+sys.executable]
        if generator: configure += ["-G",generator]
        commands = [configure,["cmake","--build",str(output),"--config","Release","--parallel","2"]]
        receipt["commands"] = commands
        with (output/"build.log").open("w",encoding="utf-8") as log:
            for command in commands: subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        binaries = [p for p in (output/"python").iterdir()
                    if p.name.startswith("g31_nowait") and any(p.name.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)]
        if len(binaries)!=1: raise RuntimeError("expected exactly one native extension")
        receipt.update(status="complete",binaries={str(p):digest(p) for p in binaries})
        save()
    except BaseException as exc:
        receipt.update(status="failed",error=repr(exc));save();raise
    return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name",required=True)
    parser.add_argument("--generator")
    args=parser.parse_args()
    print(json.dumps(build(args.name,generator=args.generator),indent=2))
