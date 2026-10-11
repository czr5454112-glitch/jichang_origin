from pathlib import Path
import hashlib,json,time,sys
import pytest

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
FILES=[ROOT/'scripts/experiments/ics_circulation_v3'/n for n in
    ('same_zone_query_probe.py','same_zone_query_coverage.py','run_same_zone_query_coverage.py')]
FILES += [ROOT/'tests'/n for n in ('test_ics_circulation_v3_same_zone_query_probe.py',
    'test_ics_circulation_v3_same_zone_query_coverage.py')]
sha=lambda:{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in FILES}
before=sha();cpu=time.process_time();wall=time.perf_counter()
code=pytest.main([str(FILES[-2]),str(FILES[-1]),'-q','--basetemp',str(ROOT/'.tmp/round7_query_coverage_recovery_measured')])
record={'exit_code':code,'source_before':before,'source_after':sha(),
    'cpu_seconds':time.process_time()-cpu,'wall_seconds':time.perf_counter()-wall,
    'resource_scope':'In-process pytest interval after imports; lower bound excluding interpreter startup and final JSON serialization.',
    'prior_unmetered_attempts':[{'tests':7,'passed':7,'tool_wall_seconds':1.4448135,'cpu_seconds':None},
        {'tests':20,'passed':20,'tool_wall_seconds':2.1702418,'cpu_seconds':None}],
    'no_physical_original_network_experiments':True}
with Path(__file__).with_name('validation_recovery_freeze.json').open('x',encoding='utf8')as f:json.dump(record,f,indent=2)
print(json.dumps(record));raise SystemExit(code)


