"""Rebuild frozen research candidate011 without changing its historical records.

Requires Python, pybind11, CMake and a configured C++17 compiler on PATH.
The new binary, receipt and two newly bound contracts live in one fresh build
directory. The frozen source and historical contracts are read-only inputs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.machinery
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = Path("outputs/experiments/g31_no_wait_20261024/candidate011")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(path):
    path = Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest(path),
                bytes=path.stat().st_size)


def rebuild(name, *, generator=None):
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("build name must contain letters, digits or underscores")
    candidate = ROOT / CANDIDATE
    templates = {}
    for label in ("original_window", "drain200000"):
        path = candidate / "registered_contracts_011" / ("physical_contract_" + label + ".json")
        raw = path.read_bytes()
        contract = json.loads(raw)
        if contract["native_source"]["sha256"] != digest(candidate / "source/core.cpp"):
            raise ValueError("candidate011 source differs from its frozen contract")
        templates[label] = (path, raw, contract)
    output = ROOT / "build" / ("g31_research_011_" + name)
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    source.mkdir()
    for filename in ("core.cpp", "CMakeLists.txt"):
        shutil.copyfile(candidate / "source" / filename, source / filename)
    receipt = dict(status="building", candidate="011", python=sys.executable,
                   python_version=sys.version,
                   source_sha256={p.name:digest(p) for p in source.iterdir()},
                   original_contracts={label:evidence(item[0]) for label,item in templates.items()})
    receipt_path = output / "build_receipt.json"

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        import pybind11
        python_output = output / "python"
        configure = ["cmake", "-S", str(source), "-B", str(output),
                     "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_TRY_COMPILE_CONFIGURATION=Release",
                     "-Dpybind11_DIR=" + pybind11.get_cmake_dir(),
                     "-DPython_EXECUTABLE=" + sys.executable,
                     "-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_RELEASE=" + str(python_output),
                     "-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE=" + str(python_output)]
        if generator:
            configure += ["-G", generator]
        commands = [configure, ["cmake", "--build", str(output), "--config", "Release", "--parallel", "2"]]
        receipt["commands"] = commands
        with (output / "build.log").open("w", encoding="utf-8") as log:
            for command in commands:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        binaries = [p for p in python_output.iterdir() if p.is_file()
                    and p.name.startswith("g31_nowait")
                    and any(p.name.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)]
        if len(binaries) != 1:
            raise RuntimeError("expected exactly one native extension in build/python")
        for filename, expected in receipt["source_sha256"].items():
            if digest(source / filename) != expected:
                raise ValueError("build source changed during compilation")
        contracts = output / "registered_contracts"
        contracts.mkdir()
        registered = {}
        for label, (path, raw, original) in templates.items():
            if path.read_bytes() != raw:
                raise ValueError("historical contract changed during rebuild")
            contract = copy.deepcopy(original)
            contract["native_source"] = evidence(source / "core.cpp")
            contract["default_binary"] = evidence(binaries[0])
            target = contracts / ("physical_contract_" + label + ".json")
            target.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            registered[label] = evidence(target)
        receipt.update(status="complete", binaries={str(binaries[0]):digest(binaries[0])},
                       registered_contracts=registered,
                       frozen_source_and_contracts_modified=False,
                       execution_entrypoint=(CANDIDATE / "run_candidate.py").as_posix())
        save()
    except BaseException as exc:
        receipt.update(status="failed", error=repr(exc))
        save()
        raise
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--generator")
    args = parser.parse_args()
    print(json.dumps(rebuild(args.name, generator=args.generator), indent=2))
