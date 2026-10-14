"""Clean-build all registered native CTest programs; no pybind or legacy overwrite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).absolute().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--vcvars",type=Path,required=True)
    parser.add_argument("--ninja",type=Path,required=True)
    args=parser.parse_args()
    out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"build_lt_native_compat"/out.name;build.mkdir(parents=True,exist_ok=False)
    files=sorted([ROOT/"CMakeLists.txt",*(p for p in ROOT.glob("cpp/**/*.hpp") if "bindings" not in p.parts),
                  *(p for p in ROOT.glob("cpp/**/*.cpp") if "bindings" not in p.parts)])
    snapshot=lambda:{p.relative_to(ROOT).as_posix():sha(p) for p in files}
    receipt={"schema":"g31.circulation.all_native_validation.v1","status":"started",
             "source_before":snapshot(),"commands":[],"build_root":str(build),"clean_first":True}
    cmake=shutil.which("cmake");ctest=shutil.which("ctest")
    commands=[[cmake,"-S",str(ROOT),"-B",str(build),"-G","Ninja",
               "-DCMAKE_BUILD_TYPE=Release","-DCMAKE_TRY_COMPILE_CONFIGURATION=Release",
               "-DCZR005_BUILD_PYBIND=OFF","-DCMAKE_MAKE_PROGRAM="+str(args.ninja.absolute())],
              [cmake,"--build",str(build),"--clean-first","--parallel","2"],
              [ctest,"--test-dir",str(build),"--output-on-failure","--output-junit",str(out/"junit.xml")]]
    started=time.perf_counter()
    try:
        for i,command in enumerate(commands):
            script=out/f"command_{i:02}.cmd"
            script.write_text('@echo off\ncall "'+str(args.vcvars.absolute())+'"\n'
                              'if errorlevel 1 exit /b %errorlevel%\n'+subprocess.list2cmdline(command)+
                              '\nexit /b %errorlevel%\n',encoding="utf-8")
            actual=["cmd.exe","/c",str(script)]
            with (out/f"command_{i:02}.stdout.log").open("wb") as stdout,(out/f"command_{i:02}.stderr.log").open("wb") as stderr:
                result=subprocess.run(actual,cwd=ROOT,stdout=stdout,stderr=stderr,check=False)
            receipt["commands"].append({"argv":command,"actual_argv":actual,"exit_code":result.returncode})
            if result.returncode: raise RuntimeError(f"command {i} failed: {result.returncode}")
        receipt["source_after"]=snapshot()
        receipt["source_changed"]=[p for p,h in receipt["source_before"].items() if receipt["source_after"].get(p)!=h]
        receipt["binary_sha256"]={str(p):sha(p) for p in build.glob("*.exe")}
        if receipt["source_changed"]: raise RuntimeError("source changed during build/verification")
        receipt["status"]="passed"
    except Exception as exc:
        receipt["status"]="failed";receipt["error"]=str(exc)
    receipt["wall_seconds"]=time.perf_counter()-started
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps({k:receipt[k] for k in ("status","wall_seconds")},indent=2))
    return 0 if receipt["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
