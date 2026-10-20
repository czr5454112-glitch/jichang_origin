"""Execute the sealed mature G31 fixture and a freshly compiled current one."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).absolute().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--vcvars",type=Path,required=True)
    args=parser.parse_args()
    out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"build_lt_checkpoint"/out.name;build.mkdir(parents=True,exist_ok=False)
    for value in (ROOT,out,build,args.vcvars):
        if any(c in str(value) for c in '\r\n"&|<>^%'):
            raise ValueError("unsupported shell metacharacter in build path")
    legacy=ROOT/"build_g31_parity"
    pinned_receipt=json.loads((legacy/"final_receipt.json").read_text(encoding="utf-8"))
    pinned=legacy/"pinned.exe"
    fixture=ROOT/"cpp/tests/g31_legacy_replay_fixture.cpp"
    sources=sorted([fixture,*(p for p in ROOT.glob("cpp/ics_core/**/*.hpp")
                             if "bindings" not in p.relative_to(ROOT).parts)])
    snapshot=lambda:{p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    receipt={"schema":"g31.circulation.legacy_parity.v1","status":"started",
             "pinned_commit":pinned_receipt["pinned_commit"],
             "pinned_receipt":str(legacy/"final_receipt.json"),
             "source_before":snapshot(),"commands":[]}
    start=time.perf_counter()
    try:
        if receipt["pinned_commit"]!="46cc46ab6bc121628fd6357e9f3c7636745fd732":
            raise RuntimeError("unexpected mature baseline identity")
        if sha(pinned)!=pinned_receipt["pinned_binary_sha256"] or sha(fixture)!=pinned_receipt["fixture_sha256"]:
            raise RuntimeError("pinned binary or fixture no longer matches original independent build receipt")
        current=build/"current.exe";script=out/"compile_current.cmd"
        script.write_text('@echo off\ncall "'+str(args.vcvars.absolute())+'"\n'
                          'if errorlevel 1 exit /b %errorlevel%\n'
                          'cl /nologo /std:c++17 /EHsc /O2 /MD /bigobj '
                          '/I"'+(ROOT/"cpp").as_posix()+'" "'+fixture.as_posix()+'" '
                          '/Fo"'+(build/"current.obj").as_posix()+'" '
                          '/Fe"'+current.as_posix()+'"\nexit /b %errorlevel%\n',encoding="utf-8")
        for name,argv in (("compile",["cmd.exe","/c",str(script)]),
                          ("pinned",[str(pinned)]),("current",[str(current)])):
            with (out/(name+".stdout.log")).open("wb") as stdout,(out/(name+".stderr.log")).open("wb") as stderr:
                result=subprocess.run(argv,cwd=ROOT,stdout=stdout,stderr=stderr,check=False)
            receipt["commands"].append({"name":name,"argv":argv,"exit_code":result.returncode})
            if result.returncode: raise RuntimeError(name+" command failed; original output retained")
        old=json.loads((out/"pinned.stdout.log").read_text());new=json.loads((out/"current.stdout.log").read_text())
        (out/"pinned_result.json").write_text(json.dumps(old,indent=2),encoding="utf-8")
        (out/"current_result.json").write_text(json.dumps(new,indent=2),encoding="utf-8")
        receipt["exactly_equal"]=old==new
        receipt["binary_sha256"]={str(pinned):sha(pinned),str(current):sha(current)}
        receipt["source_after"]=snapshot()
        receipt["source_changed"]=[p for p,h in receipt["source_before"].items() if receipt["source_after"].get(p)!=h]
        if not receipt["exactly_equal"]: raise RuntimeError("legacy deterministic projections differ")
        if receipt["source_changed"]: raise RuntimeError("current sources changed during parity check")
        receipt["status"]="passed"
    except Exception as exc:
        receipt["status"]="failed";receipt["error"]=str(exc)
    receipt["wall_seconds"]=time.perf_counter()-start
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps({k:receipt[k] for k in ("status","wall_seconds")},indent=2))
    return 0 if receipt["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
