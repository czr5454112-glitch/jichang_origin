from pathlib import Path
from hashlib import sha256
import json,sys,time
import pytest
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
files=[ROOT/'scripts/experiments/ics_circulation_v3'/n for n in ('terminal_capacity_screen.py','run_terminal_capacity_screen.py')]
tests=[ROOT/'tests'/n for n in ('test_ics_circulation_v3_terminal_capacity_screen.py','test_ics_circulation_v3_terminal_capacity_screen_audit.py','test_ics_circulation_v3_terminal_capacity_screen_runner.py')]
hashes=lambda:{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()for p in files+tests}
before=hashes();cpu=time.process_time();wall=time.perf_counter()
code=pytest.main([*[str(p)for p in tests],'-q','--basetemp',str(ROOT/'.tmp/round7_terminal_snapshot_metered')])
record={'exit_code':code,'tests':36,'source_before':before,'source_after':hashes(),
    'cpu_seconds':time.process_time()-cpu,'wall_seconds':time.perf_counter()-wall,
    'prior_unmetered_attempts':[{'passed':12,'tool_wall_seconds':1.6555996,'cpu_seconds':None},
        {'passed':14,'tool_wall_seconds':1.6326448,'cpu_seconds':None},
        {'passed':33,'tool_wall_seconds':1.7993909,'cpu_seconds':None},
        {'passed':35,'tool_wall_seconds':2.101779,'cpu_seconds':None}],
    'review_fixes':'Preserve unknown-bag invalid_request; retain paid screen and partial delegate work on exception; no frozen old source changed.',
    'resource_scope':'In-process pytest interval after imports; final JSON serialization/bootstrap excluded; old842 suite is a separate earlier invocation.'}
with Path(__file__).with_name('validation_snapshot_bound.json').open('x',encoding='utf8')as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({k:record[k]for k in ('exit_code','tests','cpu_seconds','wall_seconds')}));raise SystemExit(code)

