"""Measured, append-only authoring test invocations and frozen-source checks."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
import argparse
import io
import json
from pathlib import Path
import re
import sys
from time import process_time, perf_counter

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True)
    args=parser.parse_args();target=OUT/(args.name+'.json')
    if target.exists():raise FileExistsError(target)
    files=[ROOT/'scripts/experiments/ics_circulation_v3'/n for n in (
        'prebalance.py','runtime.py','model.py','phase4_control.py','distributed_local.py','distributed_slow.py','same_zone_supply.py')]
    files += [ROOT/'cpp/ics_core/runtime/bounded_local_pibt.hpp',ROOT/'tests/test_ics_circulation_v3_same_zone_supply.py']
    before={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()for p in files}
    stream=io.StringIO();cpu,wall=process_time(),perf_counter()
    import pytest
    with redirect_stdout(stream),redirect_stderr(stream):
        result=pytest.main(['-q','tests/test_ics_circulation_v3_same_zone_supply.py','--basetemp',str(OUT/('pytest_'+args.name))])
    cpu,wall=process_time()-cpu,perf_counter()-wall
    output=stream.getvalue()
    changed=[name for name,h in before.items()if sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    record={'schema':'ics_round6_same_zone_authoring_test_v1','exit_code':int(result),
        'cpu_seconds':cpu,'wall_seconds':wall,'resource_scope':'pytest host process including pytest import; final file serialization excluded; child subprocess CPU not measured',
        'source_sha256':before,'changed':changed,'log':output,'new_deployment_experiments':0,
        'note':'Small unit-test generator/validator calls are real; no original-map rollout or selected-episode replay.'}
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output)
    print(json.dumps({'record':str(target),'exit_code':int(result),'cpu_seconds':cpu,'wall_seconds':wall,'changed':changed}))
    raise SystemExit(int(result)or bool(changed))

if __name__=='__main__':main()
