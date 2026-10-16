"""One bounded data-only gate; separate from actual18 and its frozen sources."""
from pathlib import Path
import hashlib,json,sys,time
from scripts.experiments.g31_ics_circulation import bounded_windows_job as job
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent/'firsthop_entry_pure_001'
NAMES=['scripts/experiments/g31_ics_circulation/initial_owner_route_entry_hop.py',
       'tests/test_g31_circulation_initial_owner_route_entry_hop.py',
       'scripts/experiments/g31_ics_circulation/initial_owner_route_contract.py']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False)
if '--child' in sys.argv:
    assert sys.stdin.readline()==sha(__file__)+'\n'
    import pytest
    raise SystemExit(pytest.main(['-q',NAMES[1],'--junitxml='+str(OUT/'tests.xml'),
                                 '--basetemp='+str(OUT/'temp')]))
OUT.mkdir(exist_ok=False)
pins={p:sha(ROOT/p) for p in NAMES}
for p in NAMES:
    target=OUT/'source'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/p).read_bytes())
write(OUT/'plan.json',{'source_sha256':pins,'script_sha256':sha(__file__),
    'hard_timeout_seconds':60.,'native_calls':0,'timing_comparison':False})
began=time.perf_counter()
with (OUT/'stdout.log').open('x',encoding='utf8') as out,(OUT/'stderr.log').open('x',encoding='utf8') as err:
    process=job.run([sys.executable,str(Path(__file__).resolve()),'--child'],timeout=60.,
        stdout=out,stderr=err,admission=sha(__file__),cwd=ROOT)
unchanged=pins=={p:sha(ROOT/p) for p in NAMES}
write(OUT/'bounded_execution.json',{'process':process,'outside_seconds':time.perf_counter()-began,
    'source_unchanged':unchanged,'XML_sha256':sha(OUT/'tests.xml') if (OUT/'tests.xml').exists() else None,
    'source_sha256':pins,'native_calls':0,'new_predictions':0,'actual18_integration':False})
print(json.dumps({'process':process,'source_unchanged':unchanged,'receipt_sha256':sha(OUT/'bounded_execution.json')}))
if not unchanged or process['status']!='exited' or process['exitcode']!=0:raise SystemExit(1)
