"""Bind all author receipts without duplicating nested query/replay CPU."""
from hashlib import sha256
from pathlib import Path
import json
import time
import traceback

BASE=Path(__file__).resolve().parent
ROOT=Path.cwd()
index=1
while (BASE/f'resource_bindings_{index:03d}.json').exists():
    index+=1
OUT=BASE/f'resource_bindings_{index:03d}.json'
cpu,wall=time.process_time(),time.perf_counter()
paths=['baseline_001/result.json','authoring_001/result.json','comparison_001/result.json',
       'authoring_002/result.json','comparison_002/result.json','authoring_003/result.json','comparison_003/result.json']
result=dict(status='running',receipts=[],physics_calls=0,standalone_queries=0,checks=0)
def check(value):
    result['checks']+=1
    assert value
try:
    for name in paths:
        path=BASE/name
        raw=path.read_bytes()
        r=json.loads(raw)
        if name.startswith('authoring'):
            before=json.loads((path.parent/'before.json').read_text())
            after=r['after']
        else:
            before,after=r['source_sha256_before'],r['source_sha256_after']
        check(before==after)
        snapshot=path.parent/'source_snapshot'
        for source,digest in before.items():
            check(sha256((snapshot/source).read_bytes()).hexdigest()==digest)
        result['receipts'].append(dict(path=str(path.relative_to(ROOT)),sha256=sha256(raw).hexdigest(),
            cpu_seconds=r['cpu_seconds'],wall_seconds=r['wall_seconds'],status=r['status'],source_stable=True,
            standalone_queries=r.get('standalone_queries',0),
            physical_continuations=r.get('physical_continuations',0),
            scope=r['scope'],failed_attempt_retained=name=='authoring_001/result.json',
            unresolved_real_query_retained=name=='comparison_001/result.json'))
        if name.startswith('comparison'):
            for row in r['rows']:
                base=BASE/'baseline_001'/row['name']
                old=json.loads((base/'query.json').read_text())
                check(row['snapshot_sha256']==sha256((base/'snapshot.pickle').read_bytes()).hexdigest())
                check(row['generator_sha256']==sha256((base/'generator.pickle').read_bytes()).hexdigest())
                check(row['expansions']<=old['expansion_limit'])
                check(sum(row['diagnostics']['work_units_by_stage'].values())==row['expansions'])
                check(row['unchanged_snapshot'] and all(row['validator_acceptance']))
    frozen={key.replace('\\','/'):value for key,value in
            json.loads((BASE/'comparison_003/result.json').read_text())['source_sha256_after'].items()}
    keys=['scripts/experiments/ics_circulation_v3/storage_routing.py',
          'scripts/experiments/ics_circulation_v3/storage_calendar.py',
          'tests/test_ics_circulation_v3_storage_routing.py']
    author={key.replace('\\','/'):value for key,value in
            json.loads((BASE/'authoring_003/result.json').read_text())['after'].items()}
    result['current_source_sha256']={key:sha256((ROOT/key).read_bytes()).hexdigest() for key in keys}
    for key,value in result['current_source_sha256'].items():
        check(value==author[key])
        if key in frozen:
            check(value==frozen[key])
    result['main_receipt_cpu_seconds']=sum(r['cpu_seconds'] for r in result['receipts'])
    result['main_receipt_physical_continuations']=sum(r['physical_continuations'] for r in result['receipts'])
    result['main_receipt_standalone_queries']=sum(r['standalone_queries'] for r in result['receipts'])
    check(result['main_receipt_cpu_seconds']==7.21875)
    check(result['main_receipt_physical_continuations']==1)
    check(result['main_receipt_standalone_queries']==12)
    result['status']='passed'
except BaseException:
    result.update(status='failed',failure=traceback.format_exc())
result.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
    audit_script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='receipt/source/input hash audit only; no query or physics; report write excluded',
    nested_not_additive=['baseline continuation_cpu_seconds','all per-query CPU/wall','author test-internal query/physics'],
    unmetered_auxiliary=['one ad-hoc diagnostic author query and manual validator checks','source/topology reading','web research','code/docs/tool orchestration'])
OUT.write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('receipts','current_source_sha256')},indent=2))
raise SystemExit(0 if result['status']=='passed' else 1)
