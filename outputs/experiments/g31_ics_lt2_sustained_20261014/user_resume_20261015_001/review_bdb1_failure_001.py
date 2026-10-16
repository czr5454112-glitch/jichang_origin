"""Read retained failure evidence only; no new bind, test or model call."""
import hashlib
import json
from pathlib import Path
import time
START=time.perf_counter()
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/bdb1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(name):return json.loads((OUT/name).read_bytes())
def require(ok,why):
    if not ok:raise ValueError(why)
pins={'receipt.json':'d4b74b873b652a5fcd487e2dc82161f31c862f192f2fd818e066f106cb4ab00d',
    'report.json':'67173f0acc53a00d043fe8eeccc51cf965d295d5d120299ce40e1932706a5076',
    'actual.bounded.json':'738f8ab582f7678aa304f8faceacf4c0ee0f3d07c8dfa0740d526fae7bc35b5c',
    'external_application_wall.json':'4c1739f822d59f2d739216edaad4d5c58d585b74c5fcb9b6221e501232016f46',
    'plan.json':'3332dbaac1422a0f7285db9d635b7efea4ecfdac859bb631a57867776c0f1c20'}
for name,digest in pins.items():require(sha(OUT/name)==digest,'pin:'+name)
r,d,b,e,p=map(read,('receipt.json','report.json','actual.bounded.json','external_application_wall.json','plan.json'))
require(r['status']==d['status']=='unknown_failed_actual_dependency_domain','unknown retained')
require(r['report']=={'path':str(OUT/'report.json'),'sha256':pins['report.json']}
    and r['plan_sha256']==d['plan_sha256']==pins['plan.json'],'receipt bindings')
require(d['calls']=={'original_source_proof_calls':0,'private_proof_calls':0,'original_inventory_calls':0,'blocked_model_calls':[]},'zero proof/model counts')
q=d['probe']
require(q['stage']=='cold_bind' and q['status']=='unknown_failed_bind_or_use'
    and q['cold_bind_requests']==1 and q['warm_proof_uses']==0 and q['close_completed'] is False
    and q['stages']==[] and 'bound_source_proof:nonfinite_static_value' in q['error'],'failed dependency stage')
require(d['monitor_active'] is True and d['source_changed']==r['source_changed']==[],'monitor and sources')
require(b['process']['status']=='exited' and type(b['process']['exitcode']) is int and b['process']['exitcode']==1
    and b['process']['windows_job_kill_on_close'] is True and b['process']['child_released_only_after_job_assignment'] is True,'owned closed failure')
require(e['status']=='unknown_actual_failed_or_budget_exceeded' and e['launched'] is True
    and type(e['exitcode']) is int and e['exitcode']==1 and e['wrapper_exitcode']==1,'external failure')
f,t=e['stopwatch_frequency'],e['elapsed_ticks']
require(type(f) is int and f>0 and type(t) is int and 0<=t<=120*f and e['external_application_seconds']==t/f,'typed whole clock')
require(e['expected_pins']==e['pins_before']==e['pins_after'],'external fixed pins')
for path,digest in e['expected_pins'].items():require(sha(path)==digest,'external source')
for name,ref in e['outputs'].items():
    if ref is None:require(name in ('cold_proof.json','warm_proof.json') and not(OUT/name).exists(),'only absent unfinished proofs')
    else:require(ref['path']==str(OUT/name) and sha(ref['path'])==ref['sha256'],'output ref')
require(len(p['source_sha256'])==202 and len(p['evidence_sha256'])==22,'source/evidence domain')
for name,digest in p['source_sha256'].items():
    require(p['source_archive'][name]=='source/'+name and sha(ROOT/name)==sha(OUT/p['source_archive'][name])==digest,'source archive')
for path,digest in p['evidence_sha256'].items():require(sha(path)==digest,'evidence')
for field in ('loaded_entry','loaded_exit'):
    require(all(name in p['source_sha256'] and digest==p['source_sha256'][name] for name,digest in d[field].items()),'loaded closure')
result={'schema':'g31.bound_source_proof.root_failure_readback.v1','status':'retained_failed_actual_domain_independently_read',
    'pins':pins,'actual_attempts':1,'proof_calls':0,'warm_uses':0,'source_count':202,'evidence_count':22,
    'whole_python_seconds':t/f,'cold_bind_reported_ms':q['cold_bind_ns']/1e6,
    'reason':'Dependency traversal rejected a nonfinite static float before original proof execution. Traceback did not identify the specific dependency label.',
    'next_source_design':'Versioned exact IEEE float-bit binding including infinities/NaNs/signed zero; preserve model/JSON finite-input guards and full dependency coverage. Improve diagnostic labels. No repeat actual dispatch authorized by this record.',
    'performance_or_100ms_claim':False,'project_imports_or_reexecutions':0,'saved_review_seconds':time.perf_counter()-START}
target=OUT/'root_failure_readback_001.json'
with target.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'status':result['status'],'whole_seconds':t/f}))
