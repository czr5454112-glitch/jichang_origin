"""Standalone compiler/checksum validation; no circulation simulations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import time

ROOT = Path(__file__).absolute().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vcvars", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__).resolve(), ROOT/"cpp/ics_core/io/incremental_sha256.hpp",
             ROOT/"cpp/ics_core/io/canonical_map2_reader.hpp", ROOT/"tests/cpp/incremental_sha256_test.cpp"]
    before = {str(p.relative_to(ROOT)): sha(p) for p in files}
    for path in files:
        archive = out/"source"/path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archive)
    executable = out/"incremental_sha256_test.exe"
    command = ["cl", "/nologo", "/std:c++20", "/EHsc", "/O2", "/I"+str(ROOT/"cpp"),
               str(files[-1]), "/Fe:"+str(executable), "/Fo:"+str(out/"incremental_sha256_test.obj")]
    script = out/"compile.cmd"
    script.write_text('@echo off\ncall "'+str(args.vcvars.resolve())+'"\n'
        'if errorlevel 1 exit /b %errorlevel%\nset VSLANG=1033\n'
        +subprocess.list2cmdline(command)+'\nexit /b %errorlevel%\n', encoding="utf-8")
    receipt = {"schema": "g31.incremental_sha256_standalone.v1", "status": "running",
        "source_before": before, "native_session_executed": False, "circulation_sources_integrated": False,
        "reference": "https://csrc.nist.gov/pubs/fips/180-4/upd1/final", "cases": []}
    save = lambda: (out/"receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    save()
    started = time.perf_counter()
    try:
        process = subprocess.run(["cmd.exe", "/d", "/c", str(script)], cwd=ROOT, capture_output=True, timeout=120)
        (out/"compile.stdout.log").write_bytes(process.stdout)
        (out/"compile.stderr.log").write_bytes(process.stderr)
        receipt["compile_exit_code"] = process.returncode
        if process.returncode:
            raise RuntimeError("standalone_compile_failed")
        receipt["executable_sha256"] = sha(executable)
        generator = random.Random(20261014)
        lengths = [0,1,2,3,7,8,31,55,56,57,63,64,65,119,120,127,128,129,255,256,257,1024,4097,65537]
        samples = [(f"bytes_{n}", generator.randbytes(n)) for n in lengths]
        samples += [("abc", b"abc"), ("million_a", b"a"*1000000), ("binary_4m", bytes(range(256))*16384)]
        for name, data in samples:
            chunks = (1,7,55,56,63,64,65,127,4096) if len(data) < 70000 else (63,64,4096,65536)
            expected = [hashlib.sha256(data).hexdigest(), hashlib.sha256(data+b"X").hexdigest(),
                        hashlib.sha256(data+b"Y").hexdigest(), hashlib.sha256(data).hexdigest()]
            for chunk in chunks:
                process = subprocess.run([str(executable), str(chunk)], input=data, capture_output=True, timeout=20)
                row = {"case": name, "bytes": len(data), "chunk": chunk, "exit_code": process.returncode,
                       "expected": expected, "actual": process.stdout.decode("ascii", errors="replace").splitlines()}
                row["passed"] = process.returncode == 0 and row["actual"] == expected
                receipt["cases"].append(row)
                if not row["passed"]:
                    raise RuntimeError("checksum_mismatch:"+name+":"+str(chunk))
        receipt["status"] = "passed"
    except Exception as exc:
        receipt.update(status="failed", error=repr(exc))
    receipt["source_changed"] = [str(p.relative_to(ROOT)) for p in files if sha(p) != before[str(p.relative_to(ROOT))]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["wall_seconds"] = time.perf_counter()-started
    receipt["passed_cases"] = sum(row["passed"] for row in receipt["cases"])
    save()
    print(json.dumps({key: receipt[key] for key in ("status", "passed_cases", "wall_seconds", "source_changed")}))
    return int(receipt["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
