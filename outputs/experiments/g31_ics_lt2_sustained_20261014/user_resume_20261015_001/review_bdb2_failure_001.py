"""Read retained failure evidence only; no new bind, test or model call."""
import hashlib
import json
from pathlib import Path
import time
START=time.perf_counter()
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/bdb2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(name):return json.loads((OUT/name).read_bytes())
def require(ok,why):
    if not ok:raise ValueError(why)
pins={'receipt.json':'48a37a6e8ad0b17a0ec43e34ba04ff566100c51f3e3b152614f5c26e60e1f854',
    'report.json':'123317d561f9f0b72ceaef038d8ef249ac760f5aae9dde294e31210c34487934',
    'actual.bounded.json':'fab293bc7de7c6155f68cf9a58ef4bb937f1af4dfcf9473ebd7baa38876bfbd7',
    'external_application_wall.json':'83fb0666946db0fe78163fba4ecc20b0013a642fae98b935356acad1f08ecbfb',
    'plan.json':'2c2dc98fd018b8bb454847f5af67864d3012ae0e752df858fbc62ad2b4ed0ed7'}
for name,digest in pins.items():require(sha(OUT/name)==digest,'pin:'+name)
r,d,b,e,p=map(read,('receipt.json','report.json','actual.bounded.json','external_application_wall.json','plan.json'))
require(r['status']==d['status']=='unknown_failed_actual_dependency_domain','unknown retained')
require(r['report']=={'path':str(OUT/'report.json'),'sha256':pins['report.json']}
    and r['plan_sha256']==d['plan_sha256']==pins['plan.json'],'receipt bindings')
require(d['calls']=={'original_source_proof_calls':0,'private_proof_calls':0,'original_inventory_calls':0,'blocked_model_calls':[]},'zero proof/model counts')
q=d['probe']
require(q['stage']=='cold_bind' and q['status']=='unknown_failed_bind_or_use'
    and q['cold_bind_requests']==1 and q['warm_proof_uses']==0 and q['close_completed'] is False
    and q['stages']==[] and 'bound_source_proof:unsupported_static_object' in q['error']
    and 'dependency_label=root:original_proof:_source_inventory:core.build_parts:lazy.check_sources:previous.check_sources:original.annotations' in q['error'],'failed dependency stage')
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
require(len(p['source_sha256'])==209 and len(p['evidence_sha256'])==461,'source/evidence domain')
for name,digest in p['source_sha256'].items():
    require(p['source_archive'][name]=='source/'+name and sha(ROOT/name)==sha(OUT/p['source_archive'][name])==digest,'source archive')
for path,digest in p['evidence_sha256'].items():require(sha(path)==digest,'evidence')
for field in ('loaded_entry','loaded_exit'):
    require(all(name in p['source_sha256'] and digest==p['source_sha256'][name] for name,digest in d[field].items()),'loaded closure')
result={'schema':'g31.bound_source_proof.root_failure_readback.v1','status':'retained_failed_actual_domain_independently_read',
    'pins':pins,'actual_attempts':1,'proof_calls':0,'warm_uses':0,'source_count':209,'evidence_count':461,
    'whole_python_seconds':t/f,'cold_bind_reported_ms':q['cold_bind_ns']/1e6,
    'reason':'Dependency traversal rejected an unsupported static object at original.annotations before original proof execution. Full exact dependency label remains in the saved traceback. This attempt did not validate the complete dependency domain.',
    'next_source_design':'Versioned exact canonical __future__.annotations binding with full pinned standard-library class and instance integrity; preserve v2 static float codec, finite JSON and all dependency checks. No repeat dispatch authorized by this record.',
    'performance_or_100ms_claim':False,'project_imports_or_reexecutions':0,'saved_review_seconds':time.perf_counter()-START}
target=OUT/'root_failure_readback_001.json'
with target.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'status':result['status'],'whole_seconds':t/f}))
