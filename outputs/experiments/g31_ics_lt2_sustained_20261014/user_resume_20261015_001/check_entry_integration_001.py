"""Owned pure integration gate; all old gate tests and actual-entry negatives."""
from pathlib import Path
import hashlib,json,sys,time,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import bounded_windows_job as job
from scripts.experiments.g31_ics_circulation import initial_owner_route_image as image
from scripts.experiments.g31_ics_circulation import run_initial_owner_route_gate_pure_v2 as old
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent/'firsthop_entry_integration_pure_001'
TESTS=(*old.TESTS,'tests/test_g31_circulation_initial_owner_route_entry_hop.py',
    'tests/test_g31_circulation_initial_owner_route_entry_integration.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False)
if '--child' in sys.argv:
    assert sys.stdin.readline()==sha(__file__)+'\n'
    import pytest
    raise SystemExit(pytest.main(['-q',*TESTS,'--junitxml='+str(OUT/'tests.xml'),
                                 '--basetemp='+str(OUT/'temp')]))
OUT.mkdir(exist_ok=False);began=time.perf_counter()
files=image.source_closure(ROOT,old.modules()+tuple(p[:-3].replace('/','.') for p in TESTS[-2:]))
pins={p:hashlib.sha256(data).hexdigest() for p,data in files.items()}
for p,data in files.items():
    target=OUT/'source'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
write(OUT/'plan.json',{'source_sha256':pins,'script_sha256':sha(__file__),
    'hard_timeout_seconds':120.,'native_calls':0,'timing_comparison':False})
with (OUT/'stdout.log').open('x',encoding='utf8') as out,(OUT/'stderr.log').open('x',encoding='utf8') as err:
    process=job.run([sys.executable,str(Path(__file__).resolve()),'--child'],
        timeout=max(.001,120.-(time.perf_counter()-began)),stdout=out,stderr=err,admission=sha(__file__),cwd=ROOT)
unchanged=pins=={p:sha(ROOT/p) for p in pins}
cases=ET.parse(OUT/'tests.xml').getroot().findall('.//testcase') if (OUT/'tests.xml').exists() else []
good=bool(cases) and not any(e.tag in ('failure','error','skipped') for row in cases for e in row)
record={'status':'passed' if unchanged and good and process['status']=='exited' and process['exitcode']==0 else 'failed_or_unknown',
    'process':process,'outside_seconds':time.perf_counter()-began,'source_unchanged':unchanged,
    'XML_sha256':sha(OUT/'tests.xml') if cases else None,'tests':len(cases),
    'source_sha256':pins,'native_calls':0,'new_predictions':0,'actual18_dispatched':False}
write(OUT/'receipt.json',record)
print(json.dumps({k:v for k,v in record.items() if k!='source_sha256'}))
if record['status']!='passed':raise SystemExit(1)
