"""Measured author validation; every attempt is append-only."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
from pathlib import Path
import json
import sys
import time
import traceback
import xml.etree.ElementTree as ET

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
BASE=Path(__file__).resolve().parent
index=1
while (BASE/f'authoring_{index:03d}').exists(): index+=1
OUT=BASE/f'authoring_{index:03d}'
OUT.mkdir()
cpu,wall=time.process_time(),time.perf_counter()
TEST=ROOT/'tests/test_ics_v3_storage_terminal_screen.py'
paths=sorted((ROOT/'scripts/experiments/ics_circulation_v3').glob('*.py'))+[TEST,Path(__file__)]
before={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:
    target=OUT/'source_snapshot'/p.relative_to(ROOT)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(p.read_bytes())
report=dict(status='running',source_sha256_before=before,physical_runs=0,standalone_routing_queries=0)
try:
    import pytest
    from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
    from scripts.experiments.ics_circulation_v3.storage_terminal_screen import StorageTerminalScreenGenerator
    depth=[0]
    originals=[]
    def counter(function):
        def call(*args,**kwargs):
            if depth[0]==0: report['standalone_routing_queries']+=1
            depth[0]+=1
            try: return function(*args,**kwargs)
            finally: depth[0]-=1
        return call
    for cls in (StorageCandidateGenerator,StorageTerminalScreenGenerator):
        for name in ('generate','generate_empty'):
            originals.append((cls,name,getattr(cls,name)))
            setattr(cls,name,counter(getattr(cls,name)))
    try:
        with (OUT/'stdout.txt').open('w',encoding='utf-8') as stdout,(OUT/'stderr.txt').open('w',encoding='utf-8') as stderr:
            with redirect_stdout(stdout),redirect_stderr(stderr):
                code=pytest.main(['-q',str(TEST),'--junitxml='+str(OUT/'junit.xml')])
    finally:
        for cls,name,function in originals: setattr(cls,name,function)
    suites=ET.parse(OUT/'junit.xml').getroot().findall('testsuite')
    report['junit']={key:sum(int(s.get(key,'0')) for s in suites) for key in ('tests','failures','errors','skipped')}
    report['pytest_exit_code']=int(code)
    report['source_sha256_after']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before==report['source_sha256_after'],'source changed during tests'
    report['status']='passed' if code==0 else 'failed'
except BaseException:
    report.update(status='failed',failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
        scope='source freeze/imports/pytest/fixtures/query and cursor serialization; no advance/physical continuation; outer generator entry attempts counted including invalid calls, nested delegates not doubled',
        note='Query-count instrumentation overhead is included; not algorithm performance benchmark')
    (OUT/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256_before','source_sha256_after')},indent=2))
raise SystemExit(0 if report['status']=='passed' else 1)
