"""Saved-only independent preparation review, no model/proof imports."""
import hashlib
import json
from pathlib import Path
import time
START = time.perf_counter()
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/bdb2'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def require(value, why):
    if not value: raise ValueError(why)
pins = {
    OUT/'plan.json':'2c2dc98fd018b8bb454847f5af67864d3012ae0e752df858fbc62ad2b4ed0ed7',
    OUT/'ready.json':'e306a3e21cf49d9abc4d5ab9fbfddf249afcbad2438ba31592dc8e4cbb152e95',
    ROOT/'outputs/bdb2.prepare.bounded.json':'6769e861068a6f171d9beadb91580cc10a41c50c6cdca59a8096e0a3afc5732c',
    ROOT/'outputs/bdb2.prepare_external.json':'728e8b5ed9c2d1cb78b87ca3f03ab6aebc9d29c4f3709668d62a73ed13ae482a',
    ROOT/'outputs/invoke_bdb2_prepare.ps1':'a25788096882f4ad0ccf19d70df2f1156265e473a8bb8288be9ddbb2a05dff42',
    ROOT/'outputs/bdbp1/root_saved_review_001.json':'43eca928f7d4c72f52e88326f10e714b8c1a9e48f9009c9ec4223c859e6d3516',
    OUT/'target.json':'155ddeffe2ac3f16662342827aaa3c927a8b06e6aee4f34b07a4142a5cfe0c9b',
}
for path,digest in pins.items(): require(sha(path)==digest, 'pin:'+str(path))
p,r,b,e = map(read, (OUT/'plan.json',OUT/'ready.json',ROOT/'outputs/bdb2.prepare.bounded.json',ROOT/'outputs/bdb2.prepare_external.json'))
py='C:\\PROGRAMING\\python3.11.9\\python.exe'
module='scripts.experiments.g31_ics_circulation.diagnose_bound_source_proof_bind_v2'
plan_sha=pins[OUT/'plan.json']
scope={'cold_bind_requests':1,'maximum_original_source_proof_calls':1,'warm_facade_proof_uses':1,
    'fork_calls':0,'resume_calls':0,'engine_constructions':0,'model_predictions':0,
    'native_calls':0,'custom_data_C_loads':0,'unsupported_dependency_policy':'unknown_no_retry_no_omission'}
require(p['schema']=='g31.bound_source_proof.one_bind_one_use.v2' and p['status']=='prepared_unexecuted'
    and p['scope']==scope and p['shared_seconds']==120 and p['output_directory']==str(OUT), 'plan scope')
require(p['environment']=={'python':py,'sha256':'5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'},'python')
require(r['status']=='prepared_unexecuted' and r['plan']=={'path':str(OUT/'plan.json'),'sha256':plan_sha},'ready')
execute=[py,'-m',module,'--execute','--output',str(OUT),'--expected-plan',plan_sha]
require(r['execute_command']==execute,'exact future command')
require(b['status']=='passed' and b['mode']=='prepare' and b['shared_seconds']==120
    and b['process']['status']=='exited' and type(b['process']['exitcode']) is int and b['process']['exitcode']==0,
    'owned metadata outcome')
require(b['process']['windows_job_kill_on_close'] is True and b['process']['child_released_only_after_job_assignment'] is True,'owned lifetime')
require(len(b['command'])==9 and b['command'][:8]==[py,'-m',module,'--worker-mode','prepare','--output',str(OUT),'--admission'],'worker command')
require(b['plan']==r['plan'] and b['worker_result']=={'path':str(OUT/'ready.json'),'sha256':sha(OUT/'ready.json')},'owned artifacts')
require(e['status']=='prepared_unexecuted_with_external_bound' and e['schema']=='g31.bound_source_proof.prepare_external.v2'
    and e['launched'] is True and type(e['exitcode']) is int and e['exitcode']==0
    and type(e['wrapper_exitcode']) is int and e['wrapper_exitcode']==0 and e['error'] is None,'external outcome')
require(e['command']==[py,'-m',module,'--prepare','--output',str(OUT)]
    and e['cwd']==str(ROOT) and e['output_directory']==str(OUT),'external command')
f,t=e['stopwatch_frequency'],e['elapsed_ticks']
require(type(f) is int and f>0 and type(t) is int and 0<=t<=120*f
    and e['external_application_seconds']==t/f and e['shared_limit_seconds']==120,'whole120')
require(e['expected_pins']==e['pins_before']==e['pins_after'],'external pins')
for path,digest in e['expected_pins'].items(): require(sha(path)==digest,'current external pin')
for ref in e['outputs'].values(): require(type(ref) is dict and sha(ref['path'])==ref['sha256'],'external artifact')
require(len(p['source_sha256'])==209 and set(p['source_sha256'])==set(p['source_archive']),'source domain')
seen=set(); maximum=0
for name,digest in p['source_sha256'].items():
    current=(ROOT/name).resolve(); target=(OUT/p['source_archive'][name]).resolve()
    require(not Path(name).is_absolute() and Path(name).as_posix()==name and '..' not in Path(name).parts
        and p['source_archive'][name]=='source/'+name,'canonical source')
    require(current.is_relative_to(ROOT) and target.is_relative_to(OUT/'source') and current!=target
        and target not in seen and len(str(target))<260,'independent contained archive')
    seen.add(target); maximum=max(maximum,len(str(target)))
    require(sha(current)==sha(target)==digest,'source/archive:'+name)
require(len(p['evidence_sha256'])==461,'evidence denominator')
for path,digest in p['evidence_sha256'].items(): require(sha(path)==digest,'evidence:'+path)
require(p['target']=={'path':str(OUT/'target.json'),'sha256':pins[OUT/'target.json']}
    and (OUT/'target.json').read_bytes()==(ROOT/'outputs/si65d1/proofs/00.json').read_bytes(),'complete target')
for name in ('receipt.json','report.json','cold_proof.json','warm_proof.json','actual.claim.json'):
    require(not (OUT/name).exists(),'actual not yet dispatched')
require(sha(ROOT/'outputs/bdbv2p1/root_saved_review_001.json')=='e8a65188f8c104d317b5b5f631b4e7f0b083479768c5d714d087753356045941','root8')
wiring=p['required_wiring_pure']
require(wiring['expected_tests']==8 and wiring['output_directory']==str(ROOT/'outputs/bdbv2p1'),'mandatory8')
for item in (*wiring['artifacts'].values(),wiring['wrapper']):
    require(sha(item['path'])==item['sha256']==p['evidence_sha256'][item['path']],'required8_provenance')
require(p['candidate_integration_source_proof']['inverse_worker_AST'] is True
    and p['candidate_integration_source_proof']['whole_owned_parent_and_main_unchanged'] is True
    and p['binder_v2_source_proof']['schema']=='g31.request_owned_bound_future_fork.v2','candidate_v2')
for item in p['failed_v1_preserved'].values():require(sha(item['path'])==item['sha256'],'failed_v1_stays')
record={'schema':'g31.bound_source_proof.root_prelaunch_review.v1','status':'prepared_saved_bindings_verified_actual_unexecuted',
    'plan':r['plan'],'pins':{str(k):v for k,v in pins.items()},'sources':209,'evidence':461,'max_archive_path':maximum,
    'metadata_whole_seconds':t/f,'execute_command':execute,'scope':scope,'source_review_complete':True,
    'review_imported_project_code':False,'actual_proof_model_native_C_calls':0,
    'complete100ms_or_speed_claim':False,'saved_review_seconds':time.perf_counter()-START}
target=OUT/'root_prelaunch_review_001.json'
with target.open('x',encoding='utf8') as stream: json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps({'status':record['status'],'path':str(target),'sha256':sha(target),'sources':209,'metadata_whole_seconds':t/f}))
